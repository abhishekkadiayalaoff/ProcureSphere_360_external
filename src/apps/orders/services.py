from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.budgets.models import Budget, SpendLedger
from apps.organization.models import CostCenter
from apps.vendors.models import Vendor

from .models import POAmendment, POLine, PurchaseOrder


@transaction.atomic
def generate_purchase_order_service(
    *,
    vendor: Vendor,
    cost_center: CostCenter,
    line_items: list,
    created_by_user: User,
    requisition=None,
    sourcing_event=None,
    terms_and_conditions: str = "Standard HPE Enterprise Procurement Terms & Conditions",
    tax_rate: Decimal = Decimal("0.10"),
) -> PurchaseOrder:
    """
    Generates a new Purchase Order in ISSUED status from requisition/award.
    Moves BudgetReservation to SpendLedger COMMITMENT.
    """
    if vendor.status == Vendor.STATUS_SUSPENDED:
        raise ValidationError(
            f"Vendor '{vendor.legal_name}' is suspended and cannot be issued POs."
        )

    po_count = PurchaseOrder.objects.count() + 1
    po_number = f"PO-{timezone.now().strftime('%Y')}-{po_count:05d}"

    po = PurchaseOrder.objects.create(
        po_number=po_number,
        version=1,
        vendor=vendor,
        requisition=requisition,
        sourcing_event=sourcing_event,
        cost_center=cost_center,
        status=PurchaseOrder.STATUS_ISSUED,
        terms_and_conditions=terms_and_conditions,
        subtotal=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )

    subtotal = Decimal("0.00")
    for item in line_items:
        line = POLine.objects.create(
            po=po,
            item_description=item["item_description"],
            quantity=Decimal(str(item["quantity"])),
            unit_price=Decimal(str(item["unit_price"])),
            unit_of_measure=item.get("unit_of_measure", "EA"),
        )
        subtotal += line.line_total

    tax = subtotal * tax_rate
    total = subtotal + tax

    po.subtotal = subtotal
    po.tax_amount = tax
    po.total_amount = total
    po.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

    # Move BudgetReservation to SpendLedger COMMITMENT
    budget = Budget.objects.filter(cost_center=cost_center).order_by("-created_at").first()
    if budget:
        budget.committed_amount += total
        budget.save(update_fields=["committed_amount", "updated_at"])

        SpendLedger.objects.create(
            budget=budget,
            entry_type=SpendLedger.ENTRY_COMMITMENT,
            amount=total,
            reference_number=po.po_number,
            description=f"PO Commitment for {vendor.legal_name}",
        )

    AuditLog.objects.create(
        actor=created_by_user,
        action=AuditLog.ACTION_CREATE,
        target_model="PurchaseOrder",
        target_object_id=str(po.id),
        new_state={
            "po_number": po.po_number,
            "version": po.version,
            "total_amount": str(po.total_amount),
            "vendor": vendor.legal_name,
        },
    )

    return po


@transaction.atomic
def acknowledge_purchase_order_service(*, po: PurchaseOrder, vendor_user: User) -> PurchaseOrder:
    """
    Vendor acknowledges an issued PO. Transitions status to ACKNOWLEDGED.
    """
    if po.status != PurchaseOrder.STATUS_ISSUED:
        raise ValidationError(f"Cannot acknowledge PO in status '{po.status}'. Must be ISSUED.")

    previous_status = po.status
    po.status = PurchaseOrder.STATUS_ACKNOWLEDGED
    po.acknowledged_at = timezone.now()
    po.save(update_fields=["status", "acknowledged_at", "updated_at"])

    AuditLog.objects.create(
        actor=vendor_user,
        action=AuditLog.ACTION_UPDATE,
        target_model="PurchaseOrder",
        target_object_id=str(po.id),
        previous_state={"status": previous_status},
        new_state={"status": po.status, "acknowledged_at": str(po.acknowledged_at)},
    )

    return po


@transaction.atomic
def amend_purchase_order_service(
    *,
    po: PurchaseOrder,
    reason: str,
    updated_line_items: list,
    requested_by_user: User,
    tax_rate: Decimal = Decimal("0.10"),
) -> POAmendment:
    """
    Creates a PO Change Order / Amendment:
    - Captures immutable JSON snapshot of prior PO state.
    - Increments PO version counter (e.g. V1 -> V2).
    - Preserves prior POLine history in POAmendment record.
    """
    if not reason:
        raise ValidationError("Amendment justification reason is required.")

    # 1. Take JSON snapshot of previous version
    snapshot = {
        "po_number": po.po_number,
        "version": po.version,
        "subtotal": str(po.subtotal),
        "tax_amount": str(po.tax_amount),
        "total_amount": str(po.total_amount),
        "status": po.status,
        "lines": [
            {
                "description": line.item_description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "line_total": str(line.line_total),
            }
            for line in po.lines.all()
        ],
    }

    amendment_count = po.amendments.count() + 1
    amendment = POAmendment.objects.create(
        po=po,
        amendment_number=amendment_count,
        reason=reason,
        previous_version_snapshot=snapshot,
        requested_by=requested_by_user,
    )

    # 2. Update PO version and line items
    po.version += 1
    po.lines.all().delete()

    subtotal = Decimal("0.00")
    for item in updated_line_items:
        line = POLine.objects.create(
            po=po,
            item_description=item["item_description"],
            quantity=Decimal(str(item["quantity"])),
            unit_price=Decimal(str(item["unit_price"])),
            unit_of_measure=item.get("unit_of_measure", "EA"),
        )
        subtotal += line.line_total

    tax = subtotal * tax_rate
    total = subtotal + tax

    po.subtotal = subtotal
    po.tax_amount = tax
    po.total_amount = total
    po.save(update_fields=["version", "subtotal", "tax_amount", "total_amount", "updated_at"])

    AuditLog.objects.create(
        actor=requested_by_user,
        action=AuditLog.ACTION_UPDATE,
        target_model="PurchaseOrder",
        target_object_id=str(po.id),
        previous_state={"version": snapshot["version"], "total_amount": snapshot["total_amount"]},
        new_state={
            "version": po.version,
            "total_amount": str(po.total_amount),
            "amendment_number": amendment.amendment_number,
        },
    )

    return amendment
