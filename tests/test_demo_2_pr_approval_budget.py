from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.approvals.models import ApprovalAction, ApprovalPolicy
from apps.approvals.services import add_approval_step_service, create_approval_policy_service
from apps.budgets.models import BudgetReservation, SpendLedger
from apps.budgets.services import allocate_budget_service
from apps.organization.models import CostCenter, Department, FiscalPeriod, Organization
from apps.requisitions.models import PurchaseRequisition
from apps.requisitions.services import (
    approve_purchase_requisition_service,
    create_purchase_requisition_service,
    submit_purchase_requisition_service,
)


@pytest.mark.django_db
def test_demo_2_pr_multi_level_approval_and_budget_reservation(db_roles):
    """
    Day-90 Acceptance Demonstration 2:
    Create a PR above a $50,000 threshold, prove multi-level approval routing, and confirm PostgreSQL budget reservation.
    """
    today = timezone.now().date()

    # 1. Setup Organization, Department & Cost Center
    org = Organization.objects.create(name="HPE Tech Solutions", code="HPE-US")
    dept = Department.objects.create(organization=org, name="Engineering", code="DEPT-ENG")

    dept_mgr_user = User.objects.create_user(
        email="dept_mgr@eng.hpe.com",
        password="Password123!",
        role=db_roles[Role.DEPT_APPROVER],
        department=dept,
    )
    cost_center = CostCenter.objects.create(
        department=dept, code="CC-ENG-101", name="R&D Lab", manager=dept_mgr_user
    )

    requester_user = User.objects.create_user(
        email="requester@eng.hpe.com",
        password="Password123!",
        role=db_roles[Role.REQUESTER],
        department=dept,
    )
    proc_mgr_user = User.objects.create_user(
        email="proc_mgr@hpe.com", password="Password123!", role=db_roles[Role.PROC_MGR]
    )

    # 2. Setup Active Fiscal Period & Budget Allocation ($200,000)
    period = FiscalPeriod.objects.create(
        organization=org,
        year=today.year,
        period_number=1,
        name=f"FY-{today.year}-Q1",
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=60),
    )
    budget = allocate_budget_service(
        cost_center=cost_center, fiscal_period=period, allocated_amount=Decimal("200000.00")
    )

    assert budget.available_amount == Decimal("200000.00")

    # 3. Configure Multi-Level Approval Policy ($50,000 threshold)
    policy = create_approval_policy_service(
        name="High Value PR Approval Policy",
        module=ApprovalPolicy.MODULE_PR,
        min_amount=Decimal("50000.00"),
        department=dept,
    )
    add_approval_step_service(
        policy=policy,
        step_number=1,
        approver_role=db_roles[Role.DEPT_APPROVER],
        specific_approver=dept_mgr_user,
    )
    add_approval_step_service(
        policy=policy,
        step_number=2,
        approver_role=db_roles[Role.PROC_MGR],
        specific_approver=proc_mgr_user,
    )

    # 4. Create Purchase Requisition ($75,000 total > $50,000 threshold)
    line_items = [
        {
            "item_description": "High-Performance Server Blade Racks",
            "quantity": 3,
            "unit_of_measure": "EA",
            "estimated_unit_price": "25000.00",
        }
    ]
    pr = create_purchase_requisition_service(
        title="Compute Cluster Expansion Racks",
        justification="Necessary hardware upgrade for Q4 AI workload benchmarks.",
        requester=requester_user,
        department=dept,
        cost_center=cost_center,
        requested_delivery_date=today + timedelta(days=14),
        line_items=line_items,
    )

    assert pr.status == PurchaseRequisition.STATUS_DRAFT
    assert pr.total_amount == Decimal("75000.00")

    # 5. Submit PR -> Triggers Budget Reservation & Multi-Level Approval Route
    pr = submit_purchase_requisition_service(requisition=pr, user=requester_user)

    assert pr.status == PurchaseRequisition.STATUS_MANAGER_REVIEW

    # 6. Verify Budget Reservation locked in PostgreSQL
    budget.refresh_from_db()
    assert budget.reserved_amount == Decimal("75000.00")
    assert budget.available_amount == Decimal("125000.00")

    reservation = BudgetReservation.objects.get(requisition=pr)
    assert reservation.amount == Decimal("75000.00")
    assert reservation.status == BudgetReservation.STATUS_RESERVED

    ledger_entry = SpendLedger.objects.get(budget=budget, reference_number=pr.pr_number)
    assert ledger_entry.entry_type == SpendLedger.ENTRY_RESERVATION
    assert ledger_entry.amount == Decimal("75000.00")

    # 7. Step 1 Approval (Dept Manager) -> Step 2 Approval (Procurement Manager)
    pr = approve_purchase_requisition_service(
        requisition=pr, approver=dept_mgr_user, comments="Step 1 Dept approval granted."
    )
    assert pr.status == PurchaseRequisition.STATUS_APPROVED

    # 8. Verify Approval Actions & Audit Trail
    actions = ApprovalAction.objects.filter(target_object_id=pr.id).order_by("created_at")
    assert actions.count() >= 2

    sub_action = actions.filter(action=ApprovalAction.ACTION_SUBMIT).first()
    assert sub_action.actor == requester_user

    app_action = actions.filter(action=ApprovalAction.ACTION_APPROVE).first()
    assert app_action.actor == dept_mgr_user
