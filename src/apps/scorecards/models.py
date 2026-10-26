from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class VendorScorecard(TimeStampedModel):
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="scorecards"
    )
    evaluation_period = models.CharField(max_length=50)  # e.g., Q1-2026

    # All indicator scores are 0-100 and NULL when no transactional data exists for the
    # indicator (never fabricated). PRD 3.3: delivery, quality, price, responsiveness,
    # compliance and SLA.
    delivery_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0-100: share of GRNs received on/before the expected delivery date",
    )
    quality_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0-100: accepted quantity / received quantity",
    )
    price_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0-100: invoiced value adherence to PO value (over-billing penalised)",
    )
    compliance_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0-100 based on vendor KYC/governance status",
    )
    responsiveness_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0-100: RFQ invitation response rate and PO acknowledgement rate",
    )
    sla_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="0-100: vendor contract obligations fulfilled on/before due date",
    )

    composite_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Weighted score over available core indicators",
    )
    evaluator_comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="evaluated_scorecards"
    )

    # Existing approved weighting for the four core indicators. Responsiveness and SLA are
    # reported but not weighted (see docs/assumptions.md ASSUMP-012, OPEN DECISION).
    CORE_WEIGHTS = {
        "delivery_score": Decimal("0.30"),
        "quality_score": Decimal("0.30"),
        "price_score": Decimal("0.20"),
        "compliance_score": Decimal("0.20"),
    }

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["vendor", "created_at"], name="scorecard_vendor_ts_idx")]

    def save(self, *args, **kwargs):
        # Weighted average re-normalised over indicators that have data.
        available = {
            field: weight
            for field, weight in self.CORE_WEIGHTS.items()
            if getattr(self, field) is not None
        }
        total_weight = sum(available.values(), Decimal("0"))
        if total_weight:
            weighted = sum(
                (Decimal(getattr(self, f)) * w for f, w in available.items()), Decimal("0")
            )
            self.composite_score = round(weighted / total_weight, 2)
        else:
            self.composite_score = None
        super().save(*args, **kwargs)

    @property
    def indicator_rows(self):
        return [
            ("Delivery", self.delivery_score),
            ("Quality", self.quality_score),
            ("Price", self.price_score),
            ("Responsiveness", self.responsiveness_score),
            ("Compliance", self.compliance_score),
            ("SLA", self.sla_score),
        ]

    def __str__(self):
        return f"Scorecard: {self.vendor.legal_name} [{self.evaluation_period}] Score: {self.composite_score}"
