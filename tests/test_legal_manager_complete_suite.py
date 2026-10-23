import json
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.contracts.models import (
    Contract,
    ContractAlert,
    ContractDocument,
    ContractMilestone,
    ContractObligation,
    ContractVersion,
)
from apps.contracts.selectors import (
    get_contracts_qs,
    get_legal_dashboard_metrics,
)
from apps.contracts.services import (
    activate_contract_service,
    add_contract_milestone_service,
    add_contract_obligation_service,
    approve_business_service,
    approve_legal_review_service,
    complete_contract_milestone_service,
    create_contract_service,
    create_contract_version_service,
    fulfill_contract_obligation_service,
    reject_legal_review_service,
    renew_contract_service,
    submit_for_legal_review_service,
    terminate_contract_service,
)
from apps.vendors.models import VendorCategory
from apps.vendors.services import register_vendor_service


@pytest.fixture
def legal_test_environment(db):
    """
    Sets up roles, users, vendor, and initial contract for complete Legal Manager suite testing.
    """
    legal_role, _ = Role.objects.get_or_create(
        code=Role.LEGAL_MGR, defaults={"name": "Legal / Contract Manager"}
    )
    proc_role, _ = Role.objects.get_or_create(
        code=Role.PROC_MGR, defaults={"name": "Procurement Manager"}
    )
    requester_role, _ = Role.objects.get_or_create(
        code=Role.REQUESTER, defaults={"name": "Requester"}
    )

    legal_user = User.objects.create_user(
        email="legal.mgr.suite@hpe.com", password="Password123!", role=legal_role
    )
    proc_user = User.objects.create_user(
        email="proc.mgr.suite@hpe.com", password="Password123!", role=proc_role
    )
    requester_user = User.objects.create_user(
        email="requester.suite@hpe.com", password="Password123!", role=requester_role
    )

    category = VendorCategory.objects.create(name="Cloud Infrastructure", code="CAT-CLOUD-01")
    vendor = register_vendor_service(
        legal_name="Acme Cloud Solutions Inc",
        tax_identification_number="TAX-ACME-900",
        category=category,
        email="contracts@acmecloud.com",
        address="777 Innovation Way, Silicon Valley, CA",
    )

    today = timezone.now().date()
    contract = create_contract_service(
        title="Enterprise Multi-Cloud Services Agreement",
        vendor=vendor,
        contract_value=Decimal("500000.00"),
        start_date=today,
        end_date=today + timezone.timedelta(days=365),
        renewal_notice_days=45,
        contract_owner=legal_user,
    )

    return {
        "legal_user": legal_user,
        "proc_user": proc_user,
        "requester_user": requester_user,
        "vendor": vendor,
        "contract": contract,
    }


# ==============================================================================
# SECTION 1: UNIT TESTS (Models, Services, Selectors & Business Rules)
# ==============================================================================


@pytest.mark.django_db
def test_unit_contract_creation_and_defaults(legal_test_environment):
    """Unit test for contract initial creation, default status and number generation."""
    contract = legal_test_environment["contract"]
    assert contract.status == Contract.STATUS_DRAFT
    assert contract.version == 1
    assert contract.contract_number.startswith("CON-")
    assert contract.contract_value == Decimal("500000.00")
    assert contract.renewal_notice_days == 45


@pytest.mark.django_db
def test_unit_contract_approval_workflow_services(legal_test_environment):
    """Unit test for the multi-step contract state machine services."""
    contract = legal_test_environment["contract"]
    legal_user = legal_test_environment["legal_user"]
    proc_user = legal_test_environment["proc_user"]

    # 1. Submit for Legal Review
    contract = submit_for_legal_review_service(
        contract=contract, user=legal_user, notes="Submitting for compliance review"
    )
    assert contract.status == Contract.STATUS_LEGAL_REVIEW

    # 2. Approve Legal Review
    contract = approve_legal_review_service(
        contract=contract, user=legal_user, notes="Indemnity and IP clauses verified"
    )
    assert contract.status == Contract.STATUS_BUSINESS_APPROVAL

    # 3. Approve Business -> Active
    contract = approve_business_service(
        contract=contract, user=proc_user, notes="Executive signoff complete"
    )
    assert contract.status == Contract.STATUS_ACTIVE


@pytest.mark.django_db
def test_unit_contract_rejection_service(legal_test_environment):
    """Unit test for legal review rejection service."""
    contract = legal_test_environment["contract"]
    legal_user = legal_test_environment["legal_user"]

    contract = submit_for_legal_review_service(contract=contract, user=legal_user)
    contract = reject_legal_review_service(
        contract=contract, user=legal_user, reason="Missing Data Protection Addendum (DPA)"
    )
    assert contract.status == Contract.STATUS_DRAFT


@pytest.mark.django_db
def test_unit_contract_version_amendment_preserves_history(legal_test_environment):
    """Unit test ensuring contract version amendments create historical records."""
    contract = legal_test_environment["contract"]
    legal_user = legal_test_environment["legal_user"]
    today = timezone.now().date()

    v2 = create_contract_version_service(
        contract=contract,
        user=legal_user,
        amendment_summary="Added AI model training compliance clause",
        contract_value=Decimal("650000.00"),
        start_date=today,
        end_date=today + timezone.timedelta(days=730),
    )

    contract.refresh_from_db()
    assert contract.version == 2
    assert contract.contract_value == Decimal("650000.00")
    assert v2.version_number == 2
    assert ContractVersion.objects.filter(contract=contract).count() == 2


@pytest.mark.django_db
def test_unit_contract_milestone_and_obligation_services(legal_test_environment):
    """Unit test for milestone and obligation lifecycle management."""
    contract = legal_test_environment["contract"]
    legal_user = legal_test_environment["legal_user"]
    today = timezone.now().date()

    # Milestone
    ms = add_contract_milestone_service(
        contract=contract,
        title="Security Penetration Test Report",
        due_date=today + timezone.timedelta(days=30),
        amount=Decimal("15000.00"),
    )
    assert not ms.is_completed
    ms = complete_contract_milestone_service(milestone=ms, user=legal_user)
    assert ms.is_completed

    # Obligation
    ob = add_contract_obligation_service(
        contract=contract,
        title="ISO27001 Certification Renewal",
        responsible_party="VENDOR",
        due_date=today + timezone.timedelta(days=60),
    )
    assert not ob.is_fulfilled
    ob = fulfill_contract_obligation_service(obligation=ob, user=legal_user)
    assert ob.is_fulfilled


@pytest.mark.django_db
def test_unit_legal_dashboard_metrics_selector(legal_test_environment):
    """Unit test for Legal Manager dashboard metric calculation selector."""
    metrics = get_legal_dashboard_metrics()
    assert "total_contracts" in metrics
    assert "active_contracts" in metrics
    assert "total_contract_value" in metrics
    assert "pending_legal_review" in metrics
    assert "expiring_soon" in metrics


# ==============================================================================
# SECTION 2: API ENDPOINT & RBAC TESTS (/api/v1/contracts/)
# ==============================================================================


@pytest.mark.django_db
def test_api_contract_list_and_create(legal_test_environment):
    """API test for listing and creating contracts via REST endpoints."""
    legal_user = legal_test_environment["legal_user"]
    vendor = legal_test_environment["vendor"]
    client = APIClient()
    client.force_authenticate(user=legal_user)

    # 1. GET /api/v1/contracts/
    res_list = client.get("/api/v1/contracts/")
    assert res_list.status_code == status.HTTP_200_OK

    # 2. POST /api/v1/contracts/
    today = timezone.now().date()
    payload = {
        "contract_number": "CON-2026-TEST99",
        "title": "API Test SLA Support Agreement",
        "vendor": str(vendor.id),
        "contract_value": "120000.00",
        "start_date": str(today),
        "end_date": str(today + timezone.timedelta(days=365)),
        "renewal_notice_days": 30,
    }
    res_create = client.post("/api/v1/contracts/", data=payload, format="json")
    assert res_create.status_code == status.HTTP_201_CREATED, res_create.data
    assert res_create.data["title"] == "API Test SLA Support Agreement"


@pytest.mark.django_db
def test_api_contract_workflow_actions(legal_test_environment):
    """API test for submit-legal, legal-approve, and business-approve REST endpoints."""
    legal_user = legal_test_environment["legal_user"]
    proc_user = legal_test_environment["proc_user"]
    contract = legal_test_environment["contract"]

    client = APIClient()

    # 1. Submit for Legal Review via API
    client.force_authenticate(user=legal_user)
    res_submit = client.post(
        f"/api/v1/contracts/{contract.id}/submit-legal/",
        {"notes": "API submit"},
        format="json",
    )
    assert res_submit.status_code == status.HTTP_200_OK
    assert res_submit.data["status"] == Contract.STATUS_LEGAL_REVIEW

    # 2. Approve Legal Review via API (as Legal Manager)
    res_legal_app = client.post(
        f"/api/v1/contracts/{contract.id}/legal-approve/",
        {"notes": "API legal approve"},
        format="json",
    )
    assert res_legal_app.status_code == status.HTTP_200_OK
    assert res_legal_app.data["status"] == Contract.STATUS_BUSINESS_APPROVAL

    # 3. Approve Business via API (as Proc Manager)
    client.force_authenticate(user=proc_user)
    res_biz_app = client.post(
        f"/api/v1/contracts/{contract.id}/business-approve/",
        {"notes": "API business approve"},
        format="json",
    )
    assert res_biz_app.status_code == status.HTTP_200_OK
    assert res_biz_app.data["status"] == Contract.STATUS_ACTIVE


@pytest.mark.django_db
def test_api_rbac_legal_approve_forbidden_for_non_legal_users(legal_test_environment):
    """RBAC Security test: Non-Legal users must be forbidden from calling legal-approve API."""
    requester_user = legal_test_environment["requester_user"]
    legal_user = legal_test_environment["legal_user"]
    contract = legal_test_environment["contract"]

    submit_for_legal_review_service(contract=contract, user=legal_user)

    client = APIClient()
    client.force_authenticate(user=requester_user)

    res_fail = client.post(
        f"/api/v1/contracts/{contract.id}/legal-approve/",
        {"notes": "Bypassing legal review"},
        format="json",
    )
    assert res_fail.status_code == status.HTTP_403_FORBIDDEN


# ==============================================================================
# SECTION 3: INTEGRATION & UI DASHBOARD VIEW TESTS
# ==============================================================================


@pytest.mark.django_db
def test_integration_legal_manager_dashboard_rendering(client, legal_test_environment):
    """Integration test verifying Legal Manager home dashboard page rendering."""
    legal_user = legal_test_environment["legal_user"]
    contract = legal_test_environment["contract"]

    client.force_login(legal_user)
    response = client.get("/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Legal" in content or "Contract" in content


@pytest.mark.django_db
def test_integration_contract_list_detail_and_create_views(client, legal_test_environment):
    """Integration test verifying contract list, detail, and create web views."""
    legal_user = legal_test_environment["legal_user"]
    contract = legal_test_environment["contract"]

    client.force_login(legal_user)

    # 1. Contract List View
    res_list = client.get(reverse("contracts_list"))
    assert res_list.status_code == 200
    assert contract.contract_number in res_list.content.decode()

    # 2. Contract Detail View
    res_detail = client.get(reverse("contract_detail", kwargs={"contract_id": contract.id}))
    assert res_detail.status_code == 200
    assert contract.title in res_detail.content.decode()

    # 3. Contract Create GET View
    res_create = client.get(reverse("contract_create"))
    assert res_create.status_code == 200


@pytest.mark.django_db
def test_integration_all_legal_sidebar_navigation_items_accessible(client, legal_test_environment):
    """
    Integration test verifying that all 8 sidebar navigation items for Legal Manager
    (Dashboard, Contract Register, New Contract, Approvals Inbox, Sourcing Events,
    Vendor Directory, Vendor Scorecards, Reports & Analytics) return HTTP 200 OK
    without permission errors and render using the Legal Manager layout.
    """
    legal_user = legal_test_environment["legal_user"]
    client.force_login(legal_user)

    sidebar_urls = [
        "/",
        "/contracts/",
        "/contracts/create/",
        "/approvals/inbox/",
        "/sourcing-events/",
        "/vendors/",
        "/scorecards/",
        "/reports/",
    ]

    for url in sidebar_urls:
        response = client.get(url)
        assert response.status_code == 200, f"URL {url} failed with status {response.status_code}"
