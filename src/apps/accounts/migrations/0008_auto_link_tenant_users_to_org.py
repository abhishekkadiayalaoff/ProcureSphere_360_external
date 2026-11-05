from django.db import migrations


def link_tenant_users(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Organization = apps.get_model("organization", "Organization")

    # Target custom tenant organizations (excluding default demo orgs)
    custom_org = (
        Organization.objects.filter(name__icontains="Defence").first()
        or Organization.objects.exclude(code__in=["ORG-HPE-01", "ORG-DEMO-01", "DEFAULT"]).last()
    )
    if not custom_org:
        return

    # Specifically link sameerbasha and shaiksamreen
    target_emails = ["sameerbasha.0809@gmail.com", "shaiksamreen7981@gmail.com"]
    for email in target_emails:
        u = User.objects.filter(email__iexact=email).first()
        if u and not u.organization_id:
            u.organization = custom_org
            u.save(update_fields=["organization"])

    # If any user has department/cost_center, ensure organization is set
    for user in User.objects.filter(organization__isnull=True):
        if not user.is_superuser and user.email.lower() not in ["admin@hpe.com", "admin@procuresphere.com"]:
            if user.department and user.department.organization:
                user.organization = user.department.organization
                user.save(update_fields=["organization"])
            elif user.cost_center and user.cost_center.department and user.cost_center.department.organization:
                user.organization = user.cost_center.department.organization
                user.save(update_fields=["organization"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_enforce_demo_user_permissions"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(link_tenant_users, noop),
    ]
