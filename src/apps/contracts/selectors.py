from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models import Role

from .models import Contract, ContractAlert, ContractMilestone, ContractObligation


def get_contracts_qs(user=None, status=None, search=None):
    """
    Returns filtered and scoped contracts QuerySet.
    """
    qs = Contract.objects.select_related(
        "vendor", "contract_owner", "sourcing_event", "po"
    ).prefetch_related("milestones", "obligations", "documents", "alerts", "versions")

    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(vendor=vendor) if vendor else qs.none()

    if status:
        qs = qs.filter(status=status)

    if search:
        qs = qs.filter(
            Q(contract_number__icontains=search)
            | Q(title__icontains=search)
            | Q(vendor__legal_name__icontains=search)
        )

    return qs.order_by("-created_at")


def get_all_contracts():
    return get_contracts_qs()


def get_contract_by_id(contract_id):
    return (
        Contract.objects.select_related("vendor", "contract_owner", "sourcing_event", "po")
        .prefetch_related(
            "milestones",
            "obligations",
            "documents",
            "alerts",
            "versions",
            "versions__approved_by",
            "documents__uploaded_by",
        )
        .filter(id=contract_id)
        .first()
    )


def get_contracts_pending_legal_review():
    return get_contracts_qs(status=Contract.STATUS_LEGAL_REVIEW)


def get_expiring_contracts(days=30, user=None):
    today = timezone.now().date()
    future_date = today + timezone.timedelta(days=days)
    qs = Contract.objects.select_related("vendor", "contract_owner").filter(
        status__in=[Contract.STATUS_ACTIVE, Contract.STATUS_RENEWAL_DUE],
        end_date__lte=future_date,
    )
    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(vendor=vendor) if vendor else qs.none()
    return qs.order_by("end_date")


def get_pending_obligations(user=None):
    qs = ContractObligation.objects.select_related("contract", "contract__vendor").filter(
        is_fulfilled=False
    )
    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(contract__vendor=vendor) if vendor else qs.none()
    return qs.order_by("due_date")


def get_contract_obligations_qs(
    user=None,
    due_status=None,
    responsible_party=None,
    start_date=None,
    end_date=None,
    search=None,
):
    """
    Returns filtered and scoped ContractObligation QuerySet.
    """
    today = timezone.now().date()
    qs = ContractObligation.objects.select_related("contract", "contract__vendor")

    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(contract__vendor=vendor) if vendor else qs.none()

    if due_status:
        st = str(due_status).upper().strip()
        if st == "OVERDUE":
            qs = qs.filter(is_fulfilled=False, due_date__lt=today)
        elif st == "UPCOMING":
            qs = qs.filter(is_fulfilled=False, due_date__gte=today)
        elif st == "FULFILLED":
            qs = qs.filter(is_fulfilled=True)

    if responsible_party:
        qs = qs.filter(responsible_party__iexact=str(responsible_party).strip())

    if start_date:
        qs = qs.filter(due_date__gte=start_date)

    if end_date:
        qs = qs.filter(due_date__lte=end_date)

    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(contract__contract_number__icontains=search)
            | Q(contract__title__icontains=search)
            | Q(contract__vendor__legal_name__icontains=search)
        )

    return qs.order_by("due_date")


def get_pending_milestones(user=None):
    qs = ContractMilestone.objects.select_related("contract", "contract__vendor").filter(
        is_completed=False
    )
    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(contract__vendor=vendor) if vendor else qs.none()
    return qs.order_by("due_date")


def get_active_contract_alerts(user=None):
    qs = ContractAlert.objects.select_related("contract", "contract__vendor").filter(
        is_processed=False
    )
    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(contract__vendor=vendor) if vendor else qs.none()
    return qs.order_by("-triggered_at")


def get_legal_dashboard_metrics(user=None):
    today = timezone.now().date()
    qs = Contract.objects.all()
    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            qs = qs.filter(vendor=vendor) if vendor else qs.none()

    total_contracts = qs.count()
    active_contracts = qs.filter(
        status__in=[Contract.STATUS_ACTIVE, Contract.STATUS_RENEWED]
    ).count()
    pending_legal_review = qs.filter(status=Contract.STATUS_LEGAL_REVIEW).count()
    expiring_soon = qs.filter(
        status__in=[Contract.STATUS_ACTIVE, Contract.STATUS_RENEWAL_DUE],
        end_date__lte=today + timezone.timedelta(days=30),
    ).count()

    total_value = qs.aggregate(total=Sum("contract_value"))["total"] or 0

    obligations_qs = ContractObligation.objects.all()
    milestones_qs = ContractMilestone.objects.all()
    if user:
        role_code = getattr(user, "role_code", None) or (
            user.role.code if getattr(user, "role", None) else None
        )
        if role_code == Role.VENDOR_USER:
            vendor = getattr(user, "vendor", None)
            obligations_qs = (
                obligations_qs.filter(contract__vendor=vendor) if vendor else obligations_qs.none()
            )
            milestones_qs = (
                milestones_qs.filter(contract__vendor=vendor) if vendor else milestones_qs.none()
            )

    open_obligations = obligations_qs.filter(is_fulfilled=False).count()
    overdue_obligations = obligations_qs.filter(is_fulfilled=False, due_date__lt=today).count()
    open_milestones = milestones_qs.filter(is_completed=False).count()

    return {
        "total_contracts": total_contracts,
        "active_contracts": active_contracts,
        "pending_legal_review": pending_legal_review,
        "expiring_soon": expiring_soon,
        "total_contract_value": float(total_value),
        "open_obligations": open_obligations,
        "overdue_obligations": overdue_obligations,
        "open_milestones": open_milestones,
    }
