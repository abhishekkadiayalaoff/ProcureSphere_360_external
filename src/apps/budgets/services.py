from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.audit.models import AuditLog
from apps.organization.models import CostCenter, FiscalPeriod

from .models import Budget, BudgetReservation, SpendLedger


class BudgetOverrunException(Exception):
    def __init__(self, message, budget=None, requested_amount=None):
        self.message = message
        self.budget = budget
        self.requested_amount = requested_amount
        super().__init__(self.message)


@transaction.atomic
def allocate_budget_service(
    *,
    cost_center: CostCenter,
    fiscal_period: FiscalPeriod,
    allocated_amount: Decimal,
    allow_overspend: bool = False,
) -> Budget:
    """
    Allocates budget to a CostCenter for a FiscalPeriod inside an atomic transaction.
    """
    budget, created = Budget.objects.get_or_create(
        cost_center=cost_center,
        fiscal_period=fiscal_period,
        defaults={"allocated_amount": allocated_amount, "allow_overspend": allow_overspend},
    )
    if not created:
        budget.allocated_amount = allocated_amount
        budget.allow_overspend = allow_overspend
        budget.save(update_fields=["allocated_amount", "allow_overspend", "updated_at"])
    return budget


def validate_budget_availability_service(*, cost_center: CostCenter, amount: Decimal, today=None):
    """
    Validates if a cost center has sufficient available budget for an amount.
    Raises ValidationError if insufficient budget.
    """
    if not today:
        from django.utils import timezone

        today = timezone.now().date()

    budget = Budget.objects.filter(
        cost_center=cost_center,
        fiscal_period__start_date__lte=today,
        fiscal_period__end_date__gte=today,
        fiscal_period__is_closed=False,
    ).first()

    if not budget:
        raise ValidationError(
            f"No active fiscal period budget allocation found for Cost Center '{cost_center.code}'."
        )

    if amount > budget.available_amount and not budget.allow_overspend:
        raise ValidationError(
            f"Insufficient budget in Cost Center '{cost_center.code}'. "
            f"Requested: ${amount:,.2f}, Available: ${budget.available_amount:,.2f}."
        )

    return budget


@transaction.atomic
def check_and_reserve_budget_service(
    *, requisition, requested_by_user, force_overrun=False
) -> BudgetReservation:
    """
    Checks available budget for a PurchaseRequisition's cost center.
    If available (or forced), locks a BudgetReservation in RESERVED status and writes a SpendLedger entry.
    Raises BudgetOverrunException if insufficient funds.
    """
    cost_center = requisition.cost_center
    today = (
        requisition.created_at.date()
        if requisition.created_at
        else requisition.requested_delivery_date
    )

    budget = (
        Budget.objects.select_for_update()
        .filter(
            cost_center=cost_center,
            fiscal_period__start_date__lte=today,
            fiscal_period__end_date__gte=today,
            fiscal_period__is_closed=False,
        )
        .first()
    )

    if not budget:
        raise ValidationError(
            f"No active fiscal period budget allocation found for Cost Center '{cost_center.code}'."
        )

    amount = requisition.total_amount
    if amount > budget.available_amount and not budget.allow_overspend and not force_overrun:
        raise BudgetOverrunException(
            f"Insufficient budget in Cost Center '{cost_center.code}'. "
            f"Requested: ${amount:,.2f}, Available: ${budget.available_amount:,.2f}.",
            budget=budget,
            requested_amount=amount,
        )

    # Update reserved amount on budget
    budget.reserved_amount += amount
    budget.save(update_fields=["reserved_amount", "updated_at"])

    # Create BudgetReservation
    reservation = BudgetReservation.objects.create(
        budget=budget,
        requisition=requisition,
        amount=amount,
        status=BudgetReservation.STATUS_RESERVED,
    )

    # Record SpendLedger
    SpendLedger.objects.create(
        budget=budget,
        entry_type=SpendLedger.ENTRY_RESERVATION,
        amount=amount,
        reference_number=requisition.pr_number,
        description=f"PR Budget Reservation: {requisition.title}",
    )

    AuditLog.objects.create(
        actor=requested_by_user,
        action=AuditLog.ACTION_CREATE,
        target_model="BudgetReservation",
        target_object_id=str(reservation.id),
        new_state={
            "amount": str(amount),
            "pr_number": requisition.pr_number,
            "cost_center": cost_center.code,
        },
    )

    return reservation


@transaction.atomic
def convert_commitment_to_actual_service(*, po, invoice, user) -> SpendLedger:
    """
    Moves spend from COMMITMENT to ACTUAL when an invoice is approved/paid.
    """
    cost_center = po.cost_center
    budget = Budget.objects.filter(cost_center=cost_center).order_by("-created_at").first()
    if not budget:
        raise ValidationError(f"No budget found for Cost Center '{cost_center.code}'.")

    amount = invoice.total_amount
    if budget.committed_amount >= amount:
        budget.committed_amount -= amount
    else:
        budget.committed_amount = Decimal("0.00")
    budget.actual_amount += amount
    budget.save(update_fields=["committed_amount", "actual_amount", "updated_at"])

    ledger_entry = SpendLedger.objects.create(
        budget=budget,
        entry_type=SpendLedger.ENTRY_ACTUAL,
        amount=amount,
        reference_number=invoice.invoice_number,
        description=f"Actual Invoice Spend for PO {po.po_number}",
    )

    AuditLog.objects.create(
        actor=user,
        action=AuditLog.ACTION_UPDATE,
        target_model="Budget",
        target_object_id=str(budget.id),
        new_state={
            "actual_amount": str(budget.actual_amount),
            "invoice_number": invoice.invoice_number,
            "po_number": po.po_number,
        },
    )

    return ledger_entry


@transaction.atomic
def release_budget_reservation_service(
    *, requisition, user, reason: str = "Requisition Rejected/Cancelled"
) -> None:
    """
    Releases active budget reservations for a rejected or cancelled PurchaseRequisition.
    Deducts reserved_amount from Budget, updates BudgetReservation status to RELEASED,
    and logs AuditLog event.
    """
    reservations = BudgetReservation.objects.select_for_update().filter(
        requisition=requisition, status=BudgetReservation.STATUS_RESERVED
    )
    for res in reservations:
        budget = res.budget
        if budget.reserved_amount >= res.amount:
            budget.reserved_amount -= res.amount
        else:
            budget.reserved_amount = Decimal("0.00")
        budget.save(update_fields=["reserved_amount", "updated_at"])

        res.status = BudgetReservation.STATUS_RELEASED
        res.save(update_fields=["status", "updated_at"])

        AuditLog.objects.create(
            actor=user,
            action=AuditLog.ACTION_UPDATE,
            target_model="BudgetReservation",
            target_object_id=str(res.id),
            new_state={"status": res.status, "reason": reason},
        )
