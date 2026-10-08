from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class SourcingEvent(TimeStampedModel):
    TYPE_RFQ = "RFQ"
    TYPE_RFP = "RFP"

    EVENT_TYPE_CHOICES = [
        (TYPE_RFQ, "Request For Quotation (RFQ)"),
        (TYPE_RFP, "Request For Proposal (RFP)"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_PUBLISHED = "PUBLISHED"
    STATUS_BID_WINDOW = "BID_WINDOW"
    STATUS_TECHNICAL_REVIEW = "TECHNICAL_REVIEW"
    STATUS_COMMERCIAL_REVIEW = "COMMERCIAL_REVIEW"
    STATUS_AWARD_APPROVAL = "AWARD_APPROVAL"
    STATUS_AWARDED = "AWARDED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_BID_WINDOW, "Bid Window Open"),
        (STATUS_TECHNICAL_REVIEW, "Technical Review"),
        (STATUS_COMMERCIAL_REVIEW, "Commercial Review"),
        (STATUS_AWARD_APPROVAL, "Award Approval"),
        (STATUS_AWARDED, "Awarded"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    event_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default=TYPE_RFQ)
    requisition = models.ForeignKey(
        "requisitions.PurchaseRequisition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sourcing_events",
    )
    status = models.CharField(
        max_length=50, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True
    )

    bid_start_date = models.DateTimeField()
    bid_end_date = models.DateTimeField()
    is_sealed = models.BooleanField(default=True)
    description = models.TextField()

    def __str__(self):
        return f"{self.event_number} - {self.title} [{self.status}]"


class BidInvite(TimeStampedModel):
    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="invitations")
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="bid_invitations"
    )
    is_responded = models.BooleanField(default=False)

    class Meta:
        unique_together = ("event", "vendor")

    def __str__(self):
        return f"Invite for {self.vendor.legal_name} to {self.event.event_number}"


class VendorBid(TimeStampedModel):
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_WITHDRAWN = "WITHDRAWN"

    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_WITHDRAWN, "Withdrawn"),
    ]

    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="bids")
    vendor = models.ForeignKey("vendors.Vendor", on_delete=models.CASCADE, related_name="bids")
    bid_number = models.CharField(max_length=50, unique=True)
    total_bid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    proposal_summary = models.TextField(blank=True)

    class Meta:
        unique_together = ("event", "vendor")

    def __str__(self):
        return f"Bid {self.bid_number} by {self.vendor.legal_name} (${self.total_bid_amount})"


class BidLine(TimeStampedModel):
    bid = models.ForeignKey(VendorBid, on_delete=models.CASCADE, related_name="lines")
    pr_line = models.ForeignKey(
        "requisitions.PRLine", on_delete=models.SET_NULL, null=True, blank=True
    )
    item_description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    quoted_unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quoted_total_price = models.DecimalField(max_digits=14, decimal_places=2)

    def save(self, *args, **kwargs):
        self.quoted_total_price = self.quantity * self.quoted_unit_price
        super().save(*args, **kwargs)


class AwardDecision(TimeStampedModel):
    event = models.OneToOneField(
        SourcingEvent, on_delete=models.CASCADE, related_name="award_decision"
    )
    winning_bid = models.ForeignKey(VendorBid, on_delete=models.PROTECT, related_name="awards")
    award_reason = models.TextField()
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="approved_awards"
    )

    def __str__(self):
        return f"Award for {self.event.event_number} -> {self.winning_bid.vendor.legal_name}"
