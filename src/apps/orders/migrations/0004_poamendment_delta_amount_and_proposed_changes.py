from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0003_poamendment_approval_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="poamendment",
            name="delta_amount",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
        ),
        migrations.AddField(
            model_name="poamendment",
            name="proposed_changes",
            field=models.JSONField(blank=True, default=dict, help_text="Proposed changes to POLine items before approval"),
        ),
        migrations.AlterField(
            model_name="purchaseorder",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("APPROVAL", "In Approval"),
                    ("ISSUED", "Issued"),
                    ("ACKNOWLEDGED", "Acknowledged by Vendor"),
                    ("PARTIAL_RECEIPT", "Partial Receipt"),
                    ("COMPLETED", "Completed"),
                    ("CANCELLED", "Cancelled"),
                    ("AMENDMENT_PENDING", "Amendment Pending Approval"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=50,
            ),
        ),
    ]

