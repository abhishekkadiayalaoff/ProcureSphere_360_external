from django.db import transaction

from .models import CostCenter, Department, FiscalPeriod, Organization


@transaction.atomic
def create_organization_service(
    *, name: str, code: str, tax_identifier: str = "", address: str = ""
) -> Organization:
    """
    Service layer function to create an Organization entity inside a database transaction.
    """
    org = Organization.objects.create(
        name=name,
        code=code.upper(),
        tax_identifier=tax_identifier,
        address=address,
    )
    return org


@transaction.atomic
def create_department_service(
    *, organization: Organization, name: str, code: str, description: str = ""
) -> Department:
    """
    Service layer function to create a Department inside an Organization.
    """
    department = Department.objects.create(
        organization=organization,
        name=name,
        code=code.upper(),
        description=description,
    )
    return department


@transaction.atomic
def create_cost_center_service(
    *, department: Department, code: str, name: str, manager=None
) -> CostCenter:
    """
    Service layer function to create a Cost Center linked to a Department.
    """
    cost_center = CostCenter.objects.create(
        department=department,
        code=code.upper(),
        name=name,
        manager=manager,
    )
    return cost_center


@transaction.atomic
def create_fiscal_period_service(
    *, organization: Organization, year: int, period_number: int, name: str, start_date, end_date
) -> FiscalPeriod:
    """
    Service layer function to define a Fiscal Period.
    """
    period = FiscalPeriod.objects.create(
        organization=organization,
        year=year,
        period_number=period_number,
        name=name,
        start_date=start_date,
        end_date=end_date,
    )
    return period
