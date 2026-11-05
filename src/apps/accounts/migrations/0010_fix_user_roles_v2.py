from django.db import migrations


def fix_user_data_v2(apps, schema_editor):
    """
    Second repair pass: fix remaining corruption artifacts.
    - sameerbasha.0809@gmail.com -> FINANCE_AP role, clear names, clear must_change_password
    - shaiksamreen7981@gmail.com -> REQUESTER role, clear names, clear must_change_password
    This migration is idempotent and safe to re-run.
    Does NOT touch department or cost_center assignments.
    """
    User = apps.get_model("accounts", "User")
    Role = apps.get_model("accounts", "Role")

    finance_role = Role.objects.filter(code="FINANCE_AP").first()
    requester_role = Role.objects.filter(code="REQUESTER").first()

    # Fix sameerbasha.0809 - Finance AP for FCB org
    sameer = User.objects.filter(email__iexact="sameerbasha.0809@gmail.com").first()
    if sameer:
        fields_to_save = ["first_name", "last_name", "must_change_password", "is_staff", "is_superuser"]
        sameer.first_name = ""
        sameer.last_name = ""
        sameer.must_change_password = False
        sameer.is_staff = False
        sameer.is_superuser = False
        if finance_role and sameer.role != finance_role:
            sameer.role = finance_role
            fields_to_save.append("role")
        sameer.save(update_fields=fields_to_save)

    # Fix shaiksamreen7981 - Requester for FCB org
    samreen = User.objects.filter(email__iexact="shaiksamreen7981@gmail.com").first()
    if samreen:
        fields_to_save = ["first_name", "last_name", "must_change_password", "is_staff", "is_superuser"]
        samreen.first_name = ""
        samreen.last_name = ""
        samreen.must_change_password = False
        samreen.is_staff = False
        samreen.is_superuser = False
        if requester_role and samreen.role != requester_role:
            samreen.role = requester_role
            fields_to_save.append("role")
        samreen.save(update_fields=fields_to_save)

    # Also fix any non-superuser with SUPER_ADMIN role that has a department/org linkage
    if requester_role:
        for user in User.objects.filter(role__code="SUPER_ADMIN").exclude(is_superuser=True):
            if user.department_id is not None or user.cost_center_id is not None or user.organization_id is not None:
                user.role = requester_role
                user.first_name = ""
                user.last_name = ""
                user.must_change_password = False
                user.is_staff = False
                user.is_superuser = False
                user.save(update_fields=[
                    "role", "first_name", "last_name",
                    "must_change_password", "is_staff", "is_superuser"
                ])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_repair_corrupted_admin_roles"),
    ]

    operations = [
        migrations.RunPython(fix_user_data_v2, noop),
    ]
