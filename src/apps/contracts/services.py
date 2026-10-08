from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.vendors.models import Vendor

from .models import Contract, ContractAlert, ContractMilestone


@transaction.atomic
def create_contract_service(
    *,
    title: str,
    vendor: Vendor,
    contract_value: Decimal,
    start_date,
    end_date,
    contract_owner: User,
    renewal_notice_days: int = 30,
    sourcing_event=None,
    po=None,
) -> Contract:
    """
    Creates a new Contract in DRAFT status.
    """
    contract_count = Contract.objects.count() + 1
    contract_number = f"CON-{timezone.now().strftime('%Y')}-{contract_count:05d}"

    contract = Contract.objects.create(
        contract_number=contract_number,
        title=title,
        version=1,
        vendor=vendor,
        sourcing_event=sourcing_event,
        po=po,
        status=Contract.STATUS_DRAFT,
        contract_value=contract_value,
        start_date=start_date,
        end_date=end_date,
        renewal_notice_days=renewal_notice_days,
        contract_owner=contract_owner,
    )

    AuditLog.objects.create(
        actor=contract_owner,
        action=AuditLog.ACTION_CREATE,
        target_model="Contract",
        target_object_id=str(contract.id),
        new_state={
            "contract_number": contract.contract_number,
            "vendor": vendor.legal_name,
            "value": str(contract_value),
        },
    )

    return contract


@transaction.atomic
def activate_contract_service(*, contract: Contract, user: User) -> Contract:
    """
    Activates contract state from DRAFT / LEGAL_REVIEW to ACTIVE.
    """
    previous_status = contract.status
    contract.status = Contract.STATUS_ACTIVE
    contract.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=user,
        action=AuditLog.ACTION_APPROVE,
        target_model="Contract",
        target_object_id=str(contract.id),
        previous_state={"status": previous_status},
        new_state={"status": contract.status},
    )

    return contract


@transaction.atomic
def add_contract_milestone_service(
    *, contract: Contract, title: str, due_date, amount: Decimal = Decimal("0.00")
) -> ContractMilestone:
    """
    Adds a tracked milestone to a contract.
    """
    milestone = ContractMilestone.objects.create(
        contract=contract,
        title=title,
        due_date=due_date,
        amount=amount,
    )
    return milestone


@transaction.atomic
def scan_contract_expirations_and_milestones_service() -> int:
    """
    Scans active contracts for upcoming expirations & milestones.
    Executes scheduled Celery Beat task logic and logs alerts.
    Returns count of generated alerts.
    """
    today = timezone.now().date()
    alerts_created = 0

    # 1. Expiration scan
    active_contracts = Contract.objects.filter(status=Contract.STATUS_ACTIVE)
    for contract in active_contracts:
        notice_date = contract.end_date - timezone.timedelta(days=contract.renewal_notice_days)
        if (
            today >= notice_date
            and not ContractAlert.objects.filter(
                contract=contract, alert_type=ContractAlert.ALERT_RENEWAL
            ).exists()
        ):
            ContractAlert.objects.create(
                contract=contract,
                alert_type=ContractAlert.ALERT_RENEWAL,
                message=f"Contract '{contract.contract_number}' is reaching renewal notice period (End date: {contract.end_date}).",
            )
            contract.status = Contract.STATUS_RENEWAL_DUE
            contract.save(update_fields=["status", "updated_at"])
            alerts_created += 1

    # 2. Milestone due scan
    pending_milestones = ContractMilestone.objects.select_related("contract").filter(
        is_completed=False, due_date__lte=today + timezone.timedelta(days=7)
    )
    for milestone in pending_milestones:
        if not ContractAlert.objects.filter(
            contract=milestone.contract,
            alert_type=ContractAlert.ALERT_MILESTONE,
            message__contains=milestone.title,
        ).exists():
            ContractAlert.objects.create(
                contract=milestone.contract,
                alert_type=ContractAlert.ALERT_MILESTONE,
                message=f"Milestone '{milestone.title}' for contract '{milestone.contract.contract_number}' is due on {milestone.due_date}.",
            )
            alerts_created += 1

    return alerts_created
