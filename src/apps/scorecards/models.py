from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class VendorScorecard(TimeStampedModel):
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="scorecards"
    )
    evaluation_period = models.CharField(max_length=50)  # e.g., Q1-2026

    delivery_score = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="0-100 score based on GRN timeliness"
    )
    quality_score = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="0-100 score based on rejection rate"
    )
    price_score = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="0-100 score based on price variance"
    )
    compliance_score = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="0-100 score based on SLA/KYC"
    )

    composite_score = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Overall weighted performance score"
    )
    evaluator_comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="evaluated_scorecards"
    )

    def save(self, *args, **kwargs):
        # Calculate composite score (30% delivery, 30% quality, 20% price, 20% compliance)
        self.composite_score = (
            (self.delivery_score * Decimal("0.30"))
            + (self.quality_score * Decimal("0.30"))
            + (self.price_score * Decimal("0.20"))
            + (self.compliance_score * Decimal("0.20"))
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Scorecard: {self.vendor.legal_name} [{self.evaluation_period}] Score: {self.composite_score}"
