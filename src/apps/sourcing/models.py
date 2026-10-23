from decimal import Decimal

import django
from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_file_upload

_CHECK_KW = "condition" if django.VERSION >= (5, 1) else "check"


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

    # Detailed specifications and requirements
    technical_requirements = models.TextField(blank=True, default="")
    commercial_requirements = models.TextField(blank=True, default="")
    required_documents = models.TextField(blank=True, default="")

    # Weighted evaluation (PRD 3.3 Evaluation & Award: "weighted technical scoring").
    technical_weight = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("50.00"))
    commercial_weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("50.00")
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                **{
                    _CHECK_KW: models.Q(technical_weight__gte=0)
                    & models.Q(commercial_weight__gte=0)
                    & models.Q(technical_weight__lte=100)
                    & models.Q(commercial_weight__lte=100)
                },
                name="sourcing_event_weights_range",
            ),
        ]
        indexes = [models.Index(fields=["status", "bid_end_date"], name="sourcing_status_end_idx")]

    def __str__(self):
        return f"{self.event_number} - {self.title} [{self.status}]"

    @property
    def award_decision(self):
        """Current (pending or approved) award decision; rejected decisions stay as history."""
        return (
            self.award_decisions.filter(
                status__in=[AwardDecision.STATUS_PENDING, AwardDecision.STATUS_APPROVED]
            )
            .select_related("winning_bid__vendor", "recommended_by", "approved_by")
            .first()
        )

    @property
    def bids_visible_to_evaluators(self):
        return self.status not in (
            self.STATUS_DRAFT,
            self.STATUS_PUBLISHED,
            self.STATUS_BID_WINDOW,
            self.STATUS_CANCELLED,
        )

    @property
    def commercial_visible_to_evaluators(self):
        return self.status in (
            self.STATUS_COMMERCIAL_REVIEW,
            self.STATUS_AWARD_APPROVAL,
            self.STATUS_AWARDED,
        )


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
    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_AMENDED = "AMENDED"
    STATUS_WITHDRAWN = "WITHDRAWN"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_AMENDED, "Amended"),
        (STATUS_WITHDRAWN, "Withdrawn"),
        (STATUS_CLOSED, "Closed"),
    ]

    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="bids")
    vendor = models.ForeignKey("vendors.Vendor", on_delete=models.CASCADE, related_name="bids")
    bid_number = models.CharField(max_length=50, unique=True)
    version = models.PositiveIntegerField(default=1)
    total_bid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    proposal_summary = models.TextField(blank=True)
    technical_proposal = models.TextField(blank=True, default="")
    commercial_proposal = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("event", "vendor")

    def __str__(self):
        return f"Bid {self.bid_number} V{self.version} by {self.vendor.legal_name} (${self.total_bid_amount})"


class BidVersion(TimeStampedModel):
    """
    Immutable historical snapshot of each submitted and amended bid version.
    """

    bid = models.ForeignKey(VendorBid, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=30)
    total_bid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    proposal_summary = models.TextField(blank=True, default="")
    technical_proposal = models.TextField(blank=True, default="")
    commercial_proposal = models.TextField(blank=True, default="")
    amendment_reason = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    snapshot_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-version_number"]
        unique_together = ("bid", "version_number")

    def __str__(self):
        return f"{self.bid.bid_number} V{self.version_number} [{self.status}]"


class BidAttachment(TimeStampedModel):
    """
    Documents / attachments uploaded by vendor as part of technical or commercial bid submission.
    """

    DOC_TYPE_TECHNICAL = "TECHNICAL"
    DOC_TYPE_COMMERCIAL = "COMMERCIAL"
    DOC_TYPE_COMPLIANCE = "COMPLIANCE"
    DOC_TYPE_OTHER = "OTHER"

    DOC_CHOICES = [
        (DOC_TYPE_TECHNICAL, "Technical Proposal Attachment"),
        (DOC_TYPE_COMMERCIAL, "Commercial / Pricing Schedule"),
        (DOC_TYPE_COMPLIANCE, "Compliance / Certification"),
        (DOC_TYPE_OTHER, "Other Supporting Document"),
    ]

    bid = models.ForeignKey(VendorBid, on_delete=models.CASCADE, related_name="attachments")
    title = models.CharField(max_length=200)
    document_type = models.CharField(max_length=50, choices=DOC_CHOICES, default=DOC_TYPE_TECHNICAL)
    file = models.FileField(upload_to="bid_attachments/%Y/%m/", validators=[validate_file_upload])
    file_size = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()}) - {self.bid.bid_number}"


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
    """
    Award recommendation + approval decision. Rejected decisions are retained as history;
    at most one PENDING/APPROVED decision may exist per event.
    """

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending Approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    event = models.ForeignKey(
        SourcingEvent, on_delete=models.CASCADE, related_name="award_decisions"
    )
    winning_bid = models.ForeignKey(VendorBid, on_delete=models.PROTECT, related_name="awards")
    award_reason = models.TextField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    recommended_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="recommended_awards",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_awards",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_comments = models.TextField(blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event"],
                condition=models.Q(status__in=["PENDING", "APPROVED"]),
                name="award_one_active_decision_per_event",
            )
        ]

    def __str__(self):
        return f"Award for {self.event.event_number} -> {self.winning_bid.vendor.legal_name}"


class BidEvaluation(TimeStampedModel):
    event = models.ForeignKey(SourcingEvent, on_delete=models.CASCADE, related_name="evaluations")
    bid = models.ForeignKey(VendorBid, on_delete=models.CASCADE, related_name="evaluations")
    evaluator = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="evaluations"
    )
    technical_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    commercial_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    weighted_total_score = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    comments = models.TextField(blank=True)
    technical_evaluated_at = models.DateTimeField(null=True, blank=True)
    commercial_evaluated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["bid", "evaluator"], name="evaluation_unique_per_bid"),
            models.CheckConstraint(
                **{
                    _CHECK_KW: models.Q(technical_score__gte=0)
                    & models.Q(technical_score__lte=100)
                    & models.Q(commercial_score__gte=0)
                    & models.Q(commercial_score__lte=100)
                },
                name="evaluation_scores_range",
            ),
        ]

    def save(self, *args, **kwargs):
        event = self.event
        tech_w = (event.technical_weight if event else Decimal("50.00")) / Decimal("100")
        comm_w = (event.commercial_weight if event else Decimal("50.00")) / Decimal("100")
        self.weighted_total_score = (self.technical_score * tech_w) + (
            self.commercial_score * comm_w
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Eval for Bid {self.bid.bid_number} by {self.evaluator.email}: {self.weighted_total_score}"


class Clarification(TimeStampedModel):
    event = models.ForeignKey(
        SourcingEvent, on_delete=models.CASCADE, related_name="clarifications"
    )
    vendor = models.ForeignKey(
        "vendors.Vendor", on_delete=models.CASCADE, related_name="clarifications"
    )
    question = models.TextField()
    answer = models.TextField(blank=True)
    answered_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=[("PENDING", "Pending Response"), ("ANSWERED", "Answered")],
        default="PENDING",
    )

    def save(self, *args, **kwargs):
        if self.answer and self.status == "PENDING":
            self.status = "ANSWERED"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Clarification Q for {self.event.event_number} by {self.vendor.legal_name}"


class NegotiationNote(TimeStampedModel):
    """
    Append-only negotiation notes recorded against a bid during evaluation
    (PRD 3.3 Evaluation & Award: "negotiation notes").
    """

    event = models.ForeignKey(
        SourcingEvent, on_delete=models.CASCADE, related_name="negotiation_notes"
    )
    bid = models.ForeignKey(VendorBid, on_delete=models.CASCADE, related_name="negotiation_notes")
    author = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="negotiation_notes"
    )
    note = models.TextField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Negotiation note on {self.bid.bid_number} by {self.author.email}"
