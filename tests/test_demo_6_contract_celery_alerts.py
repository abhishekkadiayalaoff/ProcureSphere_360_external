from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.contracts.models import Contract, ContractAlert
from apps.contracts.services import (
    activate_contract_service,
    add_contract_milestone_service,
    create_contract_service,
)
from apps.contracts.tasks import scan_contract_expirations_and_milestones_task
from apps.vendors.models import VendorCategory
from apps.vendors.services import register_vendor_service


@pytest.mark.django_db
def test_demo_6_contract_milestone_and_celery_alerts():
    """
    Day-90 Acceptance Demonstration #6:
    Create a contract with milestone/renewal dates -> show scheduled Celery Beat notification execution evidence.
    """
    legal_role, _ = Role.objects.get_or_create(code=Role.LEGAL_MGR, defaults={"name": "Legal"})
    contract_owner = User.objects.create_user(
        email="legal.d6@hpe.com", password="password123", role=legal_role
    )

    category = VendorCategory.objects.create(name="Logistics D6", code="CAT-LOG-D6")
    vendor = register_vendor_service(
        legal_name="Global Logistics Tech Ltd",
        tax_identification_number="TAX-GLT-88",
        category=category,
        email="contracts@globallogistics.com",
        address="200 Logistics Blvd",
    )

    today = timezone.now().date()
    # Contract ending in 15 days, renewal notice period is 30 days -> immediately triggers RENEWAL_DUE alert
    contract = create_contract_service(
        title="Annual Freight & Logistics Service Agreement",
        vendor=vendor,
        contract_value=Decimal("150000.00"),
        start_date=today - timezone.timedelta(days=330),
        end_date=today + timezone.timedelta(days=15),
        renewal_notice_days=30,
        contract_owner=contract_owner,
    )

    # Add milestone due in 3 days
    add_contract_milestone_service(
        contract=contract,
        title="Q4 SLA Compliance Audit & Performance Review",
        due_date=today + timezone.timedelta(days=3),
        amount=Decimal("25000.00"),
    )

    # Activate Contract
    contract = activate_contract_service(contract=contract, user=contract_owner)
    assert contract.status == Contract.STATUS_ACTIVE

    # Trigger scheduled Celery Beat Task
    task_result = scan_contract_expirations_and_milestones_task()
    assert "Contract alert scan completed" in task_result

    # Verify Contract alerts generated
    contract.refresh_from_db()
    assert contract.status == Contract.STATUS_RENEWAL_DUE

    alerts = ContractAlert.objects.filter(contract=contract)
    assert alerts.count() == 2
    alert_types = [a.alert_type for a in alerts]
    assert ContractAlert.ALERT_RENEWAL in alert_types
    assert ContractAlert.ALERT_MILESTONE in alert_types
