from .models import CostCenter, Department, FiscalPeriod, Organization


def resolve_user_scope_organization(user):
    """
    Resolves the Organization to which all reads/writes of a role user must be
    scoped (backend, queryset-level isolation between organizations).

    Returns:
        Organization instance when the user is bound to one (directly or via
        their department), or None for genuinely global accounts
        (superusers / legacy org-less users).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return None
    return getattr(user, "effective_organization", None)


def get_all_organizations():
    return Organization.objects.filter(is_active=True).order_by("name")


def get_organization_by_id(org_id):
    return Organization.objects.filter(id=org_id).first()


def get_departments_by_organization(organization_id):
    return Department.objects.filter(organization_id=organization_id).order_by("name")


def get_cost_centers_by_department(department_id):
    return (
        CostCenter.objects.select_related("manager", "department")
        .filter(department_id=department_id)
        .order_by("code")
    )


def get_active_fiscal_period(organization_id, target_date):
    return FiscalPeriod.objects.filter(
        organization_id=organization_id,
        start_date__lte=target_date,
        end_date__gte=target_date,
        is_closed=False,
    ).first()
