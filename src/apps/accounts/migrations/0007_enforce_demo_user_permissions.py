from django.db import migrations


def enforce_demo_user_permissions(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Role = apps.get_model("accounts", "Role")

    super_admin_role = Role.objects.filter(code="SUPER_ADMIN").first()
    superadmin_emails = {"admin@hpe.com", "admin@procuresphere.com"}

    for user in User.objects.all():
        is_super = (user.role == super_admin_role) or (user.email.lower() in superadmin_emails)
        if not is_super:
            if user.is_superuser or user.is_staff:
                user.is_superuser = False
                user.is_staff = False
                user.save(update_fields=["is_superuser", "is_staff"])
        else:
            if not user.is_superuser or not user.is_staff:
                user.is_superuser = True
                user.is_staff = True
                user.save(update_fields=["is_superuser", "is_staff"])


def reverse_demo_user_permissions(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_user_organization"),
    ]

    operations = [
        migrations.RunPython(enforce_demo_user_permissions, reverse_demo_user_permissions),
    ]
