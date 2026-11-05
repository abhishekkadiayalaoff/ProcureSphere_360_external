from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.budgets.models import Budget, SpendLedger
from apps.budgets.services import allocate_budget_service
from apps.invoices.models import MatchException, SupplierInvoice
from apps.orders.models import PurchaseOrder
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.requisitions.models import PRLine, PurchaseRequisition
from apps.requisitions.services import (
    approve_purchase_requisition_service,
    create_purchase_requisition_service,
    submit_purchase_requisition_service,
)
from apps.vendors.models import Vendor, VendorCategory


@pytest.fixture
def workflow_setup(db):
    role_dept, _ = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Dept Approver"})
    role_fin, _ = Role.objects.get_or_create(code=Role.FINANCE_AP, defaults={"name": "Finance AP"})
    role_proc, _ = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Procurement Manager"})
    role_req, _ = Role.objects.get_or_create(code=Role.REQUESTER, defaults={"name": "Requester"})

    today = timezone.now().date()

    # 1. Primary Org (HPE)
    org_hpe = Organization.objects.create(name="HPE Global", code="HPE-GL")
    dept_hpe = Department.objects.create(organization=org_hpe, name="HPE IT", code="HPE-IT")
    cc_hpe = CostCenter.objects.create(department=dept_hpe, code="CC-HPE-1", name="HPE Infra")
    period_hpe = FiscalPeriod.objects.create(
        organization=org_hpe, year=2026, period_number=1, name="HPE-FY26-Q1",
        start_date=today - timezone.timedelta(days=10), end_date=today + timezone.timedelta(days=80),
    )
    budget_hpe = allocate_budget_service(cost_center=cc_hpe, fiscal_period=period_hpe, allocated_amount=Decimal("100000.00"))
    SpendLedger.objects.create(
        budget=budget_hpe, entry_type=SpendLedger.ENTRY_COMMITMENT,
        amount=Decimal("68200.00"), reference_number="PO-HPE-01", description="HPE committed spend"
    )

    # 2. Secondary Org (Brand New Org created by user)
    org_new = Organization.objects.create(name="Defence Aero Org", code="DEF-AERO")
    dept_new = Department.objects.create(organization=org_new, name="Aero Defence Dept", code="DEF-DEPT")
    cc_new = CostCenter.objects.create(department=dept_new, code="AT-76", name="defence")
    period_new = FiscalPeriod.objects.create(
        organization=org_new, year=2026, period_number=1, name="DEF-FY26-Q1",
        start_date=today - timezone.timedelta(days=5), end_date=today + timezone.timedelta(days=80),
    )
    budget_new = allocate_budget_service(cost_center=cc_new, fiscal_period=period_new, allocated_amount=Decimal("50000.00"))

    # Users
    fin_user_new = User.objects.create_user(
        email="sameerbasha.finance@defence.com", password="Password123!", role=role_fin, organization=org_new
    )
    dept_approver_new = User.objects.create_user(
        email="dept.approver@defence.com", password="Password123!", role=role_dept, organization=org_new, department=dept_new
    )
    proc_mgr_new = User.objects.create_user(
        email="proc.mgr@defence.com", password="Password123!", role=role_proc, organization=org_new
    )
    requester_new = User.objects.create_user(
        email="requester@defence.com", password="Password123!", role=role_req, organization=org_new, department=dept_new, cost_center=cc_new
    )

    return {
        "org_hpe": org_hpe,
        "org_new": org_new,
        "dept_new": dept_new,
        "cc_new": cc_new,
        "period_new": period_new,
        "budget_new": budget_new,
        "fin_user_new": fin_user_new,
        "dept_approver_new": dept_approver_new,
        "proc_mgr_new": proc_mgr_new,
        "requester_new": requester_new,
    }


@pytest.mark.django_db
def test_finance_dashboard_multi_tenant_isolation(client, workflow_setup):
    """
    Ensure a user in a newly created organization sees only their own data
    and does NOT leak HPE seed data ($68,200 committed spend, etc.).
    """
    client.force_login(workflow_setup["fin_user_new"])
    response = client.get(reverse("home"))
    assert response.status_code == 200

    metrics = response.context["metrics"]
    # Should be 0.0 committed spend (not $68,200 from HPE)
    assert metrics["committed_spend"] == 0.0
    assert metrics["actual_spend"] == 0.0
    assert metrics["pending_match_exceptions"] == 0

    # Department dropdown should only contain Defence Aero Org departments
    dept_ids = [d.id for d in response.context["departments"]]
    assert workflow_setup["dept_new"].id in dept_ids
    assert len(dept_ids) == 1


@pytest.mark.django_db
def test_requisition_within_budget_routes_to_finance_for_approval(workflow_setup):
    """
    Requisition within budget:
    Step 1: Department Approver
    Step 2: Finance / AP Approval
    """
    today = timezone.now().date()
    pr = create_purchase_requisition_service(
        title="Defence Radios",
        justification="Secure communications",
        requester=workflow_setup["requester_new"],
        department=workflow_setup["dept_new"],
        cost_center=workflow_setup["cc_new"],
        requested_delivery_date=today + timezone.timedelta(days=14),
        line_items=[
            {"item_description": "VHF Radio Unit", "quantity": 2, "estimated_unit_price": "5000.00"}  # $10,000 <= $50,000 budget
        ],
    )
    pr = submit_purchase_requisition_service(requisition=pr, user=workflow_setup["requester_new"])
    assert pr.status == PurchaseRequisition.STATUS_MANAGER_REVIEW

    # Step 1: Department Approver approves -> advances to Step 2
    pr = approve_purchase_requisition_service(
        requisition=pr, approver=workflow_setup["dept_approver_new"], comments="Dept approval verified."
    )
    assert pr.status == PurchaseRequisition.STATUS_MANAGER_REVIEW

    # Step 2: Finance / AP approves -> PR transitions to APPROVED
    pr = approve_purchase_requisition_service(
        requisition=pr, approver=workflow_setup["fin_user_new"], comments="Finance budget approval granted."
    )
    assert pr.status == PurchaseRequisition.STATUS_APPROVED


@pytest.mark.django_db
def test_requisition_out_of_budget_requires_procurement_manager_approval(workflow_setup):
    """
    Requisition out of budget:
    Routes to STATUS_BUDGET_REVIEW.
    Requires Procurement Manager approval to authorize overrun exception.
    """
    today = timezone.now().date()
    # Cost center budget is $50,000. Creating PR totaling $80,000 (exceeds budget)
    pr = create_purchase_requisition_service(
        title="Heavy Radar System",
        justification="Surveillance upgrade",
        requester=workflow_setup["requester_new"],
        department=workflow_setup["dept_new"],
        cost_center=workflow_setup["cc_new"],
        requested_delivery_date=today + timezone.timedelta(days=14),
        line_items=[
            {"item_description": "Radar Antenna Array", "quantity": 1, "estimated_unit_price": "80000.00"}
        ],
    )
    pr = submit_purchase_requisition_service(requisition=pr, user=workflow_setup["requester_new"])
    assert pr.status == PurchaseRequisition.STATUS_BUDGET_REVIEW

    # Finance user attempting to approve budget overrun is rejected
    with pytest.raises(ValidationError, match="Only Procurement Manager can approve a budget overrun exception"):
        approve_purchase_requisition_service(
            requisition=pr, approver=workflow_setup["fin_user_new"], comments="Finance attempting overrun"
        )

    # Procurement Manager approves budget overrun -> forced reservation -> status APPROVED
    pr = approve_purchase_requisition_service(
        requisition=pr, approver=workflow_setup["proc_mgr_new"], comments="Procurement Manager approved budget overrun."
    )
    assert pr.status == PurchaseRequisition.STATUS_APPROVED
