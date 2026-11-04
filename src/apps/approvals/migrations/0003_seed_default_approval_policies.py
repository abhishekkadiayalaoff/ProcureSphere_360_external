from decimal import Decimal
from django.db import migrations


def seed_default_policies(apps, schema_editor):
    ApprovalPolicy = apps.get_model("approvals", "ApprovalPolicy")
    ApprovalStep = apps.get_model("approvals", "ApprovalStep")
    Role = apps.get_model("accounts", "Role")

    dept_approver_role, _ = Role.objects.get_or_create(
        code="DEPT_APPROVER", defaults={"name": "Department Approver"}
    )
    proc_mgr_role, _ = Role.objects.get_or_create(
        code="PROC_MGR", defaults={"name": "Procurement Manager"}
    )

    # 1. Global PR Approval Policy (covers $0.00 and above for all departments without custom policy)
    pr_policy = ApprovalPolicy.objects.filter(
        module="PR",
        department__isnull=True,
        cost_center__isnull=True,
    ).first()
    if not pr_policy:
        pr_policy = ApprovalPolicy.objects.create(
            name="Standard PR Approval — Global",
            module="PR",
            department=None,
            cost_center=None,
            min_amount=Decimal("0.00"),
            max_amount=None,
            is_active=True,
        )

    if not pr_policy.steps.filter(step_number=1).exists():
        ApprovalStep.objects.create(
            policy=pr_policy,
            step_number=1,
            approver_role=dept_approver_role,
            description="Department Manager Approval",
        )
    if not pr_policy.steps.filter(step_number=2).exists():
        ApprovalStep.objects.create(
            policy=pr_policy,
            step_number=2,
            approver_role=proc_mgr_role,
            description="Procurement Manager Approval",
        )

    # 2. Global PO Amendment Policy
    po_amend_policy = ApprovalPolicy.objects.filter(
        module="PO_AMENDMENT",
        department__isnull=True,
        cost_center__isnull=True,
    ).first()
    if not po_amend_policy:
        po_amend_policy = ApprovalPolicy.objects.create(
            name="PO Amendment Approval — Global",
            module="PO_AMENDMENT",
            department=None,
            cost_center=None,
            min_amount=Decimal("0.00"),
            max_amount=None,
            is_active=True,
        )

    if not po_amend_policy.steps.filter(step_number=1).exists():
        ApprovalStep.objects.create(
            policy=po_amend_policy,
            step_number=1,
            approver_role=proc_mgr_role,
            description="Procurement Manager Approval",
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0002_approvalpolicy_cost_center_module_choices"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_policies, noop),
    ]
