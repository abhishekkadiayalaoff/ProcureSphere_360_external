from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.orders.models import POLine, PurchaseOrder

from .models import GoodsReceipt, InspectionRecord, ReceiptLine, RejectionRecord


@transaction.atomic
def create_goods_receipt_service(
    *,
    po: PurchaseOrder,
    received_by: User,
    receipt_items: list,
    delivery_note_number: str = "",
    remarks: str = "",
) -> GoodsReceipt:
    """
    Records a Goods Receipt Note (GRN) against a Purchase Order.
    Supports partial receipts and multiple GRNs against one PO.
    Updates POLine.quantity_received and transitions PO status (PARTIAL_RECEIPT vs COMPLETED).
    """
    if po.status not in [
        PurchaseOrder.STATUS_ISSUED,
        PurchaseOrder.STATUS_ACKNOWLEDGED,
        PurchaseOrder.STATUS_PARTIAL_RECEIPT,
    ]:
        raise ValidationError(f"Cannot record goods receipt against PO in status '{po.status}'.")

    grn_count = GoodsReceipt.objects.count() + 1
    grn_number = f"GRN-{timezone.now().strftime('%Y')}-{grn_count:05d}"

    receipt = GoodsReceipt.objects.create(
        grn_number=grn_number,
        po=po,
        received_by=received_by,
        received_date=timezone.now(),
        delivery_note_number=delivery_note_number,
        remarks=remarks,
    )

    for item in receipt_items:
        po_line_id = item.get("po_line_id") or (item["po_line"].id if "po_line" in item else None)
        po_line = POLine.objects.select_for_update().get(id=po_line_id)
        qty_received = Decimal(str(item["quantity_received"]))

        qty_accepted = Decimal(str(item.get("quantity_accepted", qty_received)))
        qty_rejected = qty_received - qty_accepted

        line = ReceiptLine.objects.create(
            receipt=receipt,
            po_line=po_line,
            quantity_received=qty_received,
            quantity_accepted=qty_accepted,
            quantity_rejected=qty_rejected,
            notes=item.get("notes", ""),
        )

        # Record inspection if notes/quality specified
        if "inspection_notes" in item:
            InspectionRecord.objects.create(
                receipt_line=line,
                inspected_by=received_by,
                passed=(qty_rejected == Decimal("0.00")),
                inspection_notes=item["inspection_notes"],
            )

        # Record rejection record if rejected items exist
        if qty_rejected > Decimal("0.00"):
            RejectionRecord.objects.create(
                receipt_line=line,
                rejected_quantity=qty_rejected,
                rejection_reason=item.get("rejection_reason", "Quality non-conformance"),
            )

        # Update cumulative quantity received on POLine
        po_line.quantity_received += qty_accepted
        po_line.save(update_fields=["quantity_received", "updated_at"])

    # Determine PO completion state
    all_completed = True
    for line in po.lines.all():
        if line.quantity_received < line.quantity:
            all_completed = False
            break

    po.status = (
        PurchaseOrder.STATUS_COMPLETED if all_completed else PurchaseOrder.STATUS_PARTIAL_RECEIPT
    )

    po.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=received_by,
        action=AuditLog.ACTION_CREATE,
        target_model="GoodsReceipt",
        target_object_id=str(receipt.id),
        new_state={
            "grn_number": receipt.grn_number,
            "po_number": po.po_number,
            "po_status": po.status,
        },
    )

    return receipt
