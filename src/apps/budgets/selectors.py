from apps.accounts.models import Role

from .models import Budget, SpendLedger


def scope_budgets_queryset(qs, user):
    """
    Enforces role and organizational scoping on Budgets:
    - Superuser: unrestricted access.
    - Vendor user: zero access (none).
    - Requester & Department Approver: restricted to their department.
    - Internal roles (Auditor, Procurement Manager, Finance AP, etc.):
      Restricted to their effective_organization. Cannot see other organizations' budgets.
    """
    if qs is None:
        qs = Budget.objects.select_related("cost_center", "fiscal_period").order_by("-created_at")
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs

    role_code = getattr(user, "role_code", None) or (
        user.role.code if hasattr(user, "role") and user.role else None
    )

    if getattr(user, "is_vendor", False) or role_code == Role.VENDOR_USER:
        return qs.none()

    if role_code == Role.REQUESTER:
        if getattr(user, "cost_center_id", None):
            return qs.filter(cost_center_id=user.cost_center_id)
        if getattr(user, "department_id", None):
            return qs.filter(cost_center__department_id=user.department_id)
        return qs.none()

    if role_code == Role.DEPT_APPROVER and getattr(user, "department_id", None):
        return qs.filter(cost_center__department_id=user.department_id)

    scoped_org = getattr(user, "effective_organization", None)
    if scoped_org:
        return qs.filter(cost_center__department__organization=scoped_org)

    if getattr(user, "is_staff", False):
        return qs

    return qs.none()


def scope_spend_ledger_queryset(qs, user):
    """
    Enforces role and organizational scoping on SpendLedger:
    - Superuser: unrestricted access.
    - Vendor user: zero access (none).
    - Requester & Department Approver: restricted to their department.
    - Internal roles (Auditor, Procurement Manager, Finance AP, etc.):
      Restricted to their effective_organization.
    """
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs

    role_code = getattr(user, "role_code", None) or (
        user.role.code if hasattr(user, "role") and user.role else None
    )

    if getattr(user, "is_vendor", False) or role_code == Role.VENDOR_USER:
        return qs.none()

    if role_code == Role.REQUESTER:
        if getattr(user, "cost_center_id", None):
            return qs.filter(budget__cost_center_id=user.cost_center_id)
        if getattr(user, "department_id", None):
            return qs.filter(budget__cost_center__department_id=user.department_id)
        return qs.none()

    if role_code == Role.DEPT_APPROVER and getattr(user, "department_id", None):
        return qs.filter(budget__cost_center__department_id=user.department_id)

    scoped_org = getattr(user, "effective_organization", None)
    if scoped_org:
        return qs.filter(budget__cost_center__department__organization=scoped_org)

    if getattr(user, "is_staff", False):
        return qs

    return qs.none()


def get_budget_by_cost_center(cost_center_id, fiscal_period_id=None):
    queryset = Budget.objects.select_related("cost_center", "fiscal_period").filter(
        cost_center_id=cost_center_id
    )
    if fiscal_period_id:
        return queryset.filter(fiscal_period_id=fiscal_period_id).first()
    return queryset.first()


def get_spend_ledger_entries(cost_center_id):
    return (
        SpendLedger.objects.select_related("budget__cost_center")
        .filter(budget__cost_center_id=cost_center_id)
        .order_by("-created_at")
    )
