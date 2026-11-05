from django.db import migrations


def enforce_tenant_admins_not_superuser(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Organization = apps.get_model("organization", "Organization")

    # Global platform admin emails that should retain is_superuser=True and is_staff=True
    platform_superadmin_emails = {
        "superadmin@procuresphere.com",
        "admin@procuresphere.com",
    }

    # Find all users linked to any organization
    org_admin_user_ids = set(
        Organization.objects.filter(admin_user__isnull=False).values_list("admin_user_id", flat=True)
    )

    for user in User.objects.all():
        has_org = (
            user.organization_id is not None
            or user.id in org_admin_user_ids
            or (user.department_id is not None and user.department and user.department.organization_id is not None)
            or (
                user.cost_center_id is not None
                and user.cost_center
                and user.cost_center.department
                and user.cost_center.department.organization_id is not None
            )
        )

        if has_org:
            # Any tenant-scoped user, including Org Admins, must not be global superuser or staff
            if user.is_superuser or user.is_staff:
                user.is_superuser = False
                user.is_staff = False
                user.save(update_fields=["is_superuser", "is_staff"])
        else:
            # Users with no organization: only platform superadmin accounts retain superuser/staff
            if user.email.lower() in platform_superadmin_emails:
                if not user.is_superuser or not user.is_staff:
                    user.is_superuser = True
                    user.is_staff = True
                    user.save(update_fields=["is_superuser", "is_staff"])


def reverse_migration(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_auto_link_tenant_users_to_org"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enforce_tenant_admins_not_superuser, reverse_migration),
    ]
