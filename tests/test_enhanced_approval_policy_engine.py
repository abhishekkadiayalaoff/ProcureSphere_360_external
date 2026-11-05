import json
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.approvals.models import ApprovalPolicy, ApprovalStep
from apps.approvals.services import (
    archive_policy_service,
    duplicate_approval_policy_service,
    evaluate_approval_chain,
    toggle_policy_status_service,
)
from apps.audit.models import AuditLog
from apps.organization.models import CostCenter, Department, Organization


@pytest.fixture
def enhanced_approval_setup(db):
    role_sa, _ = Role.objects.get_or_create(code=Role.SUPER_ADMIN, defaults={"name": "Super Admin"})
    role_dept, _ = Role.objects.get_or_create(code=Role.DEPT_APPROVER, defaults={"name": "Department Approver"})
    role_fin, _ = Role.objects.get_or_create(code=Role.FINANCE_AP, defaults={"name": "Finance AP"})
    role_proc, _ = Role.objects.get_or_create(code=Role.PROC_MGR, defaults={"name": "Procurement Manager"})
    role_exec, _ = Role.objects.get_or_create(code="CEO", defaults={"name": "Chief Executive Officer"})

    superadmin = User.objects.create_superuser(
        email="superadmin.policy@procuresphere.test",
        password="SuperPassword123!",
        role=role_sa,
    )

    org = Organization.objects.create(name="Tata Motors", code="TATA-01", is_active=True)
    org_admin = User.objects.create_user(
        email="orgadmin.tata@procuresphere.test",
        password="OrgPassword123!",
        role=role_sa,
        organization=org,
        is_staff=True,
    )

    dept = Department.objects.create(organization=org, name="Operations & Manufacturing", code="OPS-MFG")
    cc = CostCenter.objects.create(department=dept, code="CC-PUNE-01", name="Pune Plant Operations")

    return {
        "superadmin": superadmin,
        "org_admin": org_admin,
        "org": org,
        "dept": dept,
        "cc": cc,
        "role_dept": role_dept,
        "role_fin": role_fin,
        "role_proc": role_proc,
        "role_exec": role_exec,
    }


@pytest.mark.django_db
def test_policy_priority_matching_and_slabs(enhanced_approval_setup):
    """
    Tests 5-tier specificity matching:
    Tier 1: Org + Dept + CC
    Tier 2: Org + Dept
    Tier 3: Org Default (All Depts)
    Tier 4: Global Fallback
    """
    s = enhanced_approval_setup

    # Tier 3: Org Default PR Policy for PR 0 - 50,000
    p_org = ApprovalPolicy.objects.create(
        name="Tata Org Default PR Policy",
        organization=s["org"],
        module=ApprovalPolicy.MODULE_PR,
        currency="INR",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("50000.00"),
        is_active=True,
        status=ApprovalPolicy.STATUS_ACTIVE,
    )
    ApprovalStep.objects.create(policy=p_org, step_number=1, approver_role=s["role_dept"], description="Org Default Step")

    # Tier 2: Dept specific PR Policy for PR 0 - 50,000
    p_dept = ApprovalPolicy.objects.create(
        name="Tata Ops Dept PR Policy",
        organization=s["org"],
        department=s["dept"],
        module=ApprovalPolicy.MODULE_PR,
        currency="INR",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("50000.00"),
        is_active=True,
        status=ApprovalPolicy.STATUS_ACTIVE,
    )
    ApprovalStep.objects.create(policy=p_dept, step_number=1, approver_role=s["role_dept"], description="Dept Step")

    # Tier 1: Org + Dept + Cost Center specific PR Policy
    p_cc = ApprovalPolicy.objects.create(
        name="Tata Pune CC PR Policy",
        organization=s["org"],
        department=s["dept"],
        cost_center=s["cc"],
        module=ApprovalPolicy.MODULE_PR,
        currency="INR",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("50000.00"),
        is_active=True,
        status=ApprovalPolicy.STATUS_ACTIVE,
    )
    ApprovalStep.objects.create(policy=p_cc, step_number=1, approver_role=s["role_dept"], description="CC Pune Step")

    # 1. Matching with Org + Dept + CC matches Tier 1
    chain1 = evaluate_approval_chain(
        module=ApprovalPolicy.MODULE_PR,
        amount=Decimal("25000.00"),
        department=s["dept"],
        cost_center=s["cc"],
        organization=s["org"],
    )
    assert len(chain1) == 1
    assert chain1[0]["description"] == "CC Pune Step"

    # 2. Matching with another cost center falls back to Tier 2 (Dept)
    cc_other = CostCenter.objects.create(department=s["dept"], code="CC-SANAND-02", name="Sanand Plant")
    chain2 = evaluate_approval_chain(
        module=ApprovalPolicy.MODULE_PR,
        amount=Decimal("25000.00"),
        department=s["dept"],
        cost_center=cc_other,
        organization=s["org"],
    )
    assert len(chain2) == 1
    assert chain2[0]["description"] == "Dept Step"

    # 3. Matching with another department falls back to Tier 3 (Org default)
    dept_hr = Department.objects.create(organization=s["org"], name="Human Resources", code="HR-01")
    chain3 = evaluate_approval_chain(
        module=ApprovalPolicy.MODULE_PR,
        amount=Decimal("25000.00"),
        department=dept_hr,
        cost_center=None,
        organization=s["org"],
    )
    assert len(chain3) == 1
    assert chain3[0]["description"] == "Org Default Step"

    # 4. Matching for another organization with no org policy falls back to Tier 4 (Global)
    org_other = Organization.objects.create(name="External Corp", code="EXT-01")
    chain4 = evaluate_approval_chain(
        module=ApprovalPolicy.MODULE_PR,
        amount=Decimal("25000.00"),
        department=None,
        cost_center=None,
        organization=org_other,
    )
    assert len(chain4) >= 1
    assert chain4[0]["approver_role"] == s["role_dept"]


@pytest.mark.django_db
def test_exception_routing_escalation(enhanced_approval_setup):
    """
    Verifies that when a transaction exceeds the exception amount threshold,
    the designated exception approver is inserted or appended per routing behavior.
    """
    s = enhanced_approval_setup

    policy = ApprovalPolicy.objects.create(
        name="Capex Requisition Policy with Executive Exception",
        organization=s["org"],
        department=s["dept"],
        module=ApprovalPolicy.MODULE_PR,
        currency="INR",
        min_amount=Decimal("0.00"),
        max_amount=Decimal("1000000.00"),
        is_active=True,
        status=ApprovalPolicy.STATUS_ACTIVE,
        has_exception_routing=True,
        exception_amount_threshold=Decimal("200000.00"),
        exception_approver_role=s["role_exec"],
        exception_routing_behavior=ApprovalPolicy.EXCEPTION_BEHAVIOR_ADDITIONAL,
        exception_reason="High Value CEO Approval Required",
    )
    ApprovalStep.objects.create(policy=policy, step_number=1, approver_role=s["role_dept"], description="Dept Review")
    ApprovalStep.objects.create(policy=policy, step_number=2, approver_role=s["role_fin"], description="Finance Review")

    # Transaction below threshold (₹50,000) -> 2 standard steps
    normal_chain = evaluate_approval_chain(
        module=ApprovalPolicy.MODULE_PR,
        amount=Decimal("50000.00"),
        department=s["dept"],
        cost_center=s["cc"],
        organization=s["org"],
    )
    assert len(normal_chain) == 2
    assert normal_chain[0]["approver_role"] == s["role_dept"]
    assert normal_chain[1]["approver_role"] == s["role_fin"]

    # Transaction above threshold (₹250,000) -> 3 steps (CEO inserted after)
    exception_chain = evaluate_approval_chain(
        module=ApprovalPolicy.MODULE_PR,
        amount=Decimal("250000.00"),
        department=s["dept"],
        cost_center=s["cc"],
        organization=s["org"],
    )
    assert len(exception_chain) == 3
    assert exception_chain[2]["approver_role"] == s["role_exec"]
    assert "High Value CEO Approval" in exception_chain[2]["description"]


@pytest.mark.django_db
def test_policy_duplication_service(enhanced_approval_setup):
    """
    Verifies duplicating a policy creates a new Draft policy with steps cloned.
    """
    s = enhanced_approval_setup
    policy = ApprovalPolicy.objects.create(
        name="Master Procurement Policy",
        organization=s["org"],
        department=s["dept"],
        module=ApprovalPolicy.MODULE_PR,
        min_amount=Decimal("0.00"),
        max_amount=Decimal("100000.00"),
        is_active=True,
        status=ApprovalPolicy.STATUS_ACTIVE,
    )
    ApprovalStep.objects.create(policy=policy, step_number=1, approver_role=s["role_dept"])
    ApprovalStep.objects.create(policy=policy, step_number=2, approver_role=s["role_fin"])

    clone = duplicate_approval_policy_service(policy=policy, actor=s["superadmin"])
    assert clone.id != policy.id
    assert clone.name == "Copy of Master Procurement Policy"
    assert clone.status == ApprovalPolicy.STATUS_DRAFT
    assert clone.is_active is False
    assert clone.steps.count() == 2

    # Check audit log was written
    log = AuditLog.objects.filter(target_model="ApprovalPolicy", target_object_id=str(clone.id)).first()
    assert log is not None
    assert log.action == "CREATE"


@pytest.mark.django_db
def test_policy_status_toggle_and_zero_steps_block(enhanced_approval_setup):
    """
    Verifies that a policy cannot be activated if it has zero steps.
    """
    s = enhanced_approval_setup
    empty_policy = ApprovalPolicy.objects.create(
        name="Empty Incomplete Policy",
        organization=s["org"],
        module=ApprovalPolicy.MODULE_PR,
        min_amount=Decimal("0.00"),
        status=ApprovalPolicy.STATUS_DRAFT,
        is_active=False,
    )

    with pytest.raises(Exception) as excinfo:
        toggle_policy_status_service(policy=empty_policy, actor=s["superadmin"])
    assert "zero approval steps" in str(excinfo.value).lower()


@pytest.mark.django_db
def test_policy_archive_service(enhanced_approval_setup):
    """
    Verifies archiving sets status=ARCHIVED and is_active=False.
    """
    s = enhanced_approval_setup
    policy = ApprovalPolicy.objects.create(
        name="Old Expired Policy",
        organization=s["org"],
        module=ApprovalPolicy.MODULE_PR,
        min_amount=Decimal("0.00"),
        status=ApprovalPolicy.STATUS_ACTIVE,
        is_active=True,
    )
    ApprovalStep.objects.create(policy=policy, step_number=1, approver_role=s["role_dept"])

    archived = archive_policy_service(policy=policy, actor=s["superadmin"])
    assert archived.status == ApprovalPolicy.STATUS_ARCHIVED
    assert archived.is_active is False


@pytest.mark.django_db
def test_superadmin_policy_views_and_filter_and_search(enhanced_approval_setup):
    """
    Verifies the enhanced superadmin policies dashboard list, search, filter, and detail views.
    """
    s = enhanced_approval_setup
    client = Client()
    client.force_login(s["superadmin"])

    p1 = ApprovalPolicy.objects.create(
        name="IT Hardware Purchase Requisition",
        organization=s["org"],
        department=s["dept"],
        module=ApprovalPolicy.MODULE_PR,
        min_amount=Decimal("0.00"),
        max_amount=Decimal("100000.00"),
        status=ApprovalPolicy.STATUS_ACTIVE,
        is_active=True,
    )
    ApprovalStep.objects.create(policy=p1, step_number=1, approver_role=s["role_dept"])

    p2 = ApprovalPolicy.objects.create(
        name="PO Amendment Governance Policy",
        organization=s["org"],
        department=s["dept"],
        module=ApprovalPolicy.MODULE_PO_AMENDMENT,
        min_amount=Decimal("0.00"),
        status=ApprovalPolicy.STATUS_DRAFT,
        is_active=False,
    )
    ApprovalStep.objects.create(policy=p2, step_number=1, approver_role=s["role_proc"])

    # 1. Access policy list view
    resp = client.get("/superadmin/policies/")
    assert resp.status_code == 200
    content = resp.content.decode("utf-8")
    assert "IT Hardware Purchase Requisition" in content
    assert "PO Amendment Governance Policy" in content
    assert "Total Policies" in content

    # 2. Search query
    resp_q = client.get("/superadmin/policies/?q=Hardware")
    assert resp_q.status_code == 200
    content_q = resp_q.content.decode("utf-8")
    assert "IT Hardware Purchase Requisition" in content_q
    assert "PO Amendment Governance Policy" not in content_q

    # 3. Filter by Module
    resp_mod = client.get(f"/superadmin/policies/?module={ApprovalPolicy.MODULE_PO_AMENDMENT}")
    assert resp_mod.status_code == 200
    content_mod = resp_mod.content.decode("utf-8")
    assert "PO Amendment Governance Policy" in content_mod
    assert "IT Hardware Purchase Requisition" not in content_mod

    # 4. Filter by Status
    resp_stat = client.get("/superadmin/policies/?status=ACTIVE")
    assert resp_stat.status_code == 200
    content_stat = resp_stat.content.decode("utf-8")
    assert "IT Hardware Purchase Requisition" in content_stat
    assert "PO Amendment Governance Policy" not in content_stat

    # 5. Access Policy Detail Modal view
    resp_detail = client.get(f"/superadmin/policies/{p1.id}/")
    assert resp_detail.status_code == 200
    assert "IT Hardware Purchase Requisition" in resp_detail.content.decode("utf-8")

    # 6. Policy Duplicate action endpoint
    resp_dup = client.get(f"/superadmin/policies/{p1.id}/duplicate/", follow=True)
    assert resp_dup.status_code == 200
    assert ApprovalPolicy.objects.filter(name="Copy of IT Hardware Purchase Requisition").exists()

    # 7. Policy Toggle Status endpoint
    resp_toggle = client.get(f"/superadmin/policies/{p1.id}/toggle-status/", follow=True)
    assert resp_toggle.status_code == 200
    p1.refresh_from_db()
    assert p1.is_active is False
    assert p1.status == ApprovalPolicy.STATUS_DRAFT

    # 8. Policy Archive endpoint
    resp_arc = client.get(f"/superadmin/policies/{p1.id}/archive/", follow=True)
    assert resp_arc.status_code == 200
    p1.refresh_from_db()
    assert p1.status == ApprovalPolicy.STATUS_ARCHIVED


@pytest.mark.django_db
def test_policy_form_creation_with_dynamic_steps(enhanced_approval_setup):
    """
    Verifies creating a policy with dynamic steps submitted through PolicyAdminForm.
    """
    s = enhanced_approval_setup
    client = Client()
    client.force_login(s["superadmin"])

    steps_payload = [
        {
            "step_number": 1,
            "role_id": str(s["role_dept"].id),
            "description": "Dept Lead Approval",
            "is_mandatory": True,
            "step_type": "SEQUENTIAL",
            "approval_limit": "25000.00",
            "rejection_behavior": "RETURN_TO_REQUESTER",
            "escalation_hours": 24,
        },
        {
            "step_number": 2,
            "role_id": str(s["role_fin"].id),
            "description": "Finance Approval",
            "is_mandatory": True,
            "step_type": "SEQUENTIAL",
            "approval_limit": "",
            "rejection_behavior": "STOP_WORKFLOW",
            "escalation_hours": 48,
        },
    ]

    post_data = {
        "name": "Dynamic Multi-Step PR Policy",
        "module": ApprovalPolicy.MODULE_PR,
        "organization": str(s["org"].id),
        "department": str(s["dept"].id),
        "cost_center": str(s["cc"].id),
        "currency": "INR",
        "min_amount": "0.00",
        "max_amount": "50000.00",
        "is_active": "on",
        "status": ApprovalPolicy.STATUS_ACTIVE,
        "steps_data": json.dumps(steps_payload),
    }

    resp = client.post("/superadmin/policies/create/", data=post_data)
    assert resp.status_code == 200

    created = ApprovalPolicy.objects.filter(name="Dynamic Multi-Step PR Policy").first()
    assert created is not None
    assert created.is_active is True
    assert created.currency == "INR"
    assert created.steps.count() == 2

    step1 = created.steps.get(step_number=1)
    assert step1.approver_role == s["role_dept"]
    assert step1.approval_limit == Decimal("25000.00")
    assert step1.rejection_behavior == "RETURN_TO_REQUESTER"
    assert step1.escalation_hours == 24

    step2 = created.steps.get(step_number=2)
    assert step2.approver_role == s["role_fin"]
    assert step2.rejection_behavior == "STOP_WORKFLOW"
