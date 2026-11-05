from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models import Role
from apps.organization.selectors import resolve_user_scope_organization

from .models import Contract, ContractAlert, ContractMilestone, ContractObligation


def _scope_contracts_by_org(qs, user=None):
    """
    Organization isolation for contract data: a user bound to an organization
    only ever sees contracts owned by users of that organization (or contracts
    executed against that organization's POs).
    """
    org = resolve_user_scope_organization(user)
    if org:
        qs = qs.filter(
            Q(contract_owner__organization=org)
            | Q(contract_owner__department__organization=org)
            | Q(po__cost_center__department__organization=org)
        )
    return qs


def _scope_contract_children_by_org(qs, user=None, prefix="contract"):
    org = resolve_user_scope_organization(user)
    if org:
        joint_q = Q(
            **{f"{prefix}__contract_owner__organization": org}
        ) | Q(**{f"{prefix}__contract_owner__department__organization": org})
        joint_q |= Q(**{f"{prefix}__po__cost_center__department__organization": org})
        qs = qs.filter(joint_q)
    return qs


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
        elif not getattr(user, "is_superuser", False):
            scoped_org = getattr(user, "effective_organization", None)
            if scoped_org:
                qs = qs.filter(
                    Q(vendor__organization=scoped_org)
                    | Q(contract_owner__organization=scoped_org)
                ).distinct()

    qs = _scope_contracts_by_org(qs, user)

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


def get_contracts_pending_legal_review(user=None):
    return _scope_contracts_by_org(
        get_contracts_qs(status=Contract.STATUS_LEGAL_REVIEW), user
    )


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
    qs = _scope_contracts_by_org(qs, user)
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
    qs = _scope_contract_children_by_org(qs, user)
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

    qs = _scope_contract_children_by_org(qs, user)

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
    qs = _scope_contract_children_by_org(qs, user)
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
    qs = _scope_contract_children_by_org(qs, user)
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
    qs = _scope_contracts_by_org(qs, user)

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
    obligations_qs = _scope_contract_children_by_org(obligations_qs, user)
    milestones_qs = _scope_contract_children_by_org(milestones_qs, user)

    open_obligations = obligations_qs.filter(is_fulfilled=False).count()
    overdue_obligations = obligations_qs.filter(is_fulfilled=False, due_date__lt=today).count()
    open_milestones = milestones_qs.filter(is_completed=False).count()

    from apps.organization.selectors import resolve_user_scope_organization as _resolve_org
    from apps.vendors.models import VendorCredentialDispatch

    scoped_org = _resolve_org(user)
    pending_verifications_qs = VendorCredentialDispatch.objects.filter(
        legal_verification_status=VendorCredentialDispatch.LEGAL_STATUS_PENDING
    )
    if scoped_org:
        pending_verifications_qs = pending_verifications_qs.filter(
            Q(vendor__organization=scoped_org)
            | Q(vendor__organization__isnull=True)
            | Q(created_by__organization=scoped_org)
            | Q(created_by__department__organization=scoped_org)
        )
    pending_vendor_verifications = pending_verifications_qs.count()

    return {
        "total_contracts": total_contracts,
        "active_contracts": active_contracts,
        "pending_legal_review": pending_legal_review,
        "expiring_soon": expiring_soon,
        "total_contract_value": float(total_value),
        "open_obligations": open_obligations,
        "overdue_obligations": overdue_obligations,
        "open_milestones": open_milestones,
        "pending_vendor_verifications": pending_vendor_verifications,
    }


def get_pending_vendor_verifications_qs(user=None):
    """
    Returns list of records pending Legal Manager verification with pre-evaluated KYC compliance reports.
    Includes:
    1. VendorCredentialDispatch records pending legal verification.
    2. Vendors with replacement/renewed KYC documents in PENDING status,
       ensuring replacement documents enter the Legal review queue even when no credential dispatch is pending.
    Results are scoped to the requesting user's organization.
    """
    from django.db.models import Prefetch, Q

    from apps.organization.selectors import resolve_user_scope_organization
    from apps.vendors.kyc_policy import evaluate_vendor_kyc_compliance
    from apps.vendors.models import Vendor, VendorCredentialDispatch, VendorDocument

    scoped_org = resolve_user_scope_organization(user)

    doc_prefetch = Prefetch(
        "vendor__documents",
        queryset=VendorDocument.objects.select_related(
            "verified_by", "replaces_document"
        ).prefetch_related("review_history"),
    )

    dispatches_qs = VendorCredentialDispatch.objects.filter(
        legal_verification_status=VendorCredentialDispatch.LEGAL_STATUS_PENDING
    )
    if scoped_org:
        dispatches_qs = dispatches_qs.filter(
            Q(vendor__organization=scoped_org)
            | Q(vendor__organization__isnull=True)
            | Q(created_by__organization=scoped_org)
            | Q(created_by__department__organization=scoped_org)
        )
    dispatches = list(
        dispatches_qs.select_related("vendor", "vendor__category", "user", "created_by")
        .prefetch_related(doc_prefetch)
        .order_by("-created_at")
    )
    seen_vendor_ids = {d.vendor_id for d in dispatches if d.vendor_id}

    vendor_doc_prefetch = Prefetch(
        "documents",
        queryset=VendorDocument.objects.select_related(
            "verified_by", "replaces_document"
        ).prefetch_related("review_history"),
    )
    vendor_dispatch_prefetch = Prefetch(
        "credential_dispatches",
        queryset=VendorCredentialDispatch.objects.select_related("user", "created_by").order_by(
            "-created_at"
        ),
    )

    # Include vendors that have pending documents but no pending credential dispatch
    vendors_qs = Vendor.objects.filter(documents__status=VendorDocument.STATUS_PENDING)
    if scoped_org:
        vendors_qs = vendors_qs.filter(
            Q(organization=scoped_org)
            | Q(organization__isnull=True)
            | Q(created_by__organization=scoped_org)
            | Q(created_by__department__organization=scoped_org)
        )
    vendors_with_pending_docs = (
        vendors_qs
        .exclude(id__in=seen_vendor_ids)
        .select_related("category", "created_by")
        .prefetch_related(vendor_doc_prefetch, vendor_dispatch_prefetch)
        .distinct()
    )

    additional_items = []
    for vendor in vendors_with_pending_docs:
        # Use cached prefetched list instead of issuing a new SQL query per vendor
        dispatches_list = list(vendor.credential_dispatches.all())
        dispatch = dispatches_list[0] if dispatches_list else None
        if dispatch:
            additional_items.append(dispatch)
        else:

            class _VendorDocReviewItem:
                def __init__(self, v):
                    self.id = v.id
                    self.vendor = v
                    self.user = None
                    self.sent_to = v.email
                    self.created_by = v.created_by
                    self.created_at = v.created_at
                    self.legal_verification_status = "DOCUMENTS_PENDING"

            additional_items.append(_VendorDocReviewItem(vendor))

    all_items = dispatches + additional_items
    for item in all_items:
        item.kyc_compliance = evaluate_vendor_kyc_compliance(item.vendor)
    return all_items


def get_pending_documents_for_review_qs():
    """
    Returns QuerySet of VendorDocument records with status STATUS_PENDING awaiting Legal review.
    """
    from apps.vendors.models import VendorDocument

    return (
        VendorDocument.objects.filter(status=VendorDocument.STATUS_PENDING)
        .select_related("vendor", "vendor__category", "replaces_document")
        .order_by("-created_at")
    )
