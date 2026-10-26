import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("receipts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockHandoffRecord",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity_handed_off", models.DecimalField(decimal_places=2, max_digits=12)),
                ("storage_location", models.CharField(default="MAIN-WH", max_length=100)),
                ("handoff_notes", models.TextField(blank=True, default="")),
                ("handed_off_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "handed_off_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stock_handoffs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "receipt_line",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stock_handoff",
                        to="receipts.receiptline",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
