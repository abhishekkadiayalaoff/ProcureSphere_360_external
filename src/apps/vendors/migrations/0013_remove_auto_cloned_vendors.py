from django.db import migrations


def remove_auto_cloned_vendors(apps, schema_editor):
    Vendor = apps.get_model("vendors", "Vendor")
    # Delete synthetic cloned vendors that were auto-created from other organizations
    cloned_qs = Vendor.objects.filter(status_notes__startswith="Imported from master catalog")
    count = cloned_qs.count()
    if count > 0:
        cloned_qs.delete()
        print(f"Removed {count} auto-cloned vendor records.")


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vendors", "0012_merge_20261027_1504"),
    ]

    operations = [
        migrations.RunPython(remove_auto_cloned_vendors, reverse_noop),
    ]

