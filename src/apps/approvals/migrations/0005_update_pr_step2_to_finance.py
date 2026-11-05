from django.db import migrations


def update_pr_step2_to_finance(apps, schema_editor):
    ApprovalPolicy = apps.get_model("approvals", "ApprovalPolicy")
    Role = apps.get_model("accounts", "Role")

    finance_role = Role.objects.filter(code="FINANCE_AP").first()
    if not finance_role:
        return

    # Update PR approval policies step 2 to Finance
    pr_policies = ApprovalPolicy.objects.filter(module="PR")
    for policy in pr_policies:
        step2 = policy.steps.filter(step_number=2).first()
        if step2:
            step2.approver_role = finance_role
            step2.description = "Finance / AP Approval"
            step2.save(update_fields=["approver_role", "description"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0004_alter_approvalpolicy_module"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(update_pr_step2_to_finance, noop),
    ]
