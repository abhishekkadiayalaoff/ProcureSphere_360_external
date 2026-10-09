from .models import CostCenter, Department, FiscalPeriod, Organization


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
