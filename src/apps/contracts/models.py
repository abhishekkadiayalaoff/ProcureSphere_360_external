from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class Contract(TimeStampedModel):
    STATUS_DRAFT = "DRAFT"
    STATUS_LEGAL_REVIEW = "LEGAL_REVIEW"
    STATUS_BUSINESS_APPROVAL = "BUSINESS_APPROVAL"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_RENEWAL_DUE = "RENEWAL_DUE"
    STATUS_RENEWED = "RENEWED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_TERMINATED = "TERMINATED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_LEGAL_REVIEW, "Legal Review"),
        (STATUS_BUSINESS_APPROVAL, "Business Approval"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_RENEWAL_DUE, "Renewal Due"),
        (STATUS_RENEWED, "Renewed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_TERMINATED, "Terminated"),
    ]

    contract_number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=255)
    version = models.PositiveIntegerField(default=1)

    vendor = models.ForeignKey("vendors.Vendor", on_delete=models.PROTECT, related_name="contracts")
    sourcing_event = models.ForeignKey(
        "sourcing.SourcingEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
    )
    po = models.ForeignKey(
        "orders.PurchaseOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contracts",
    )

    status = models.CharField(
        max_length=50, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True
    )
    contract_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    start_date = models.DateField()
    end_date = models.DateField()
    renewal_notice_days = models.PositiveIntegerField(default=30)

    contract_owner = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="owned_contracts"
    )

    def __str__(self):
        return f"{self.contract_number} V{self.version} - {self.title} [{self.status}]"


class ContractVersion(TimeStampedModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    amendment_summary = models.TextField()
    contract_value = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="approved_contract_versions"
    )

    class Meta:
        unique_together = ("contract", "version_number")


class ContractMilestone(TimeStampedModel):
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Milestone: {self.title} (Due: {self.due_date})"


class ContractAlert(TimeStampedModel):
    ALERT_EXPIRATION = "EXPIRATION"
    ALERT_MILESTONE = "MILESTONE"
    ALERT_RENEWAL = "RENEWAL"

    ALERT_CHOICES = [
        (ALERT_EXPIRATION, "Contract Expiration Warning"),
        (ALERT_MILESTONE, "Milestone Due Warning"),
        (ALERT_RENEWAL, "Renewal Notice Required"),
    ]

    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="alerts")
    alert_type = models.CharField(max_length=30, choices=ALERT_CHOICES)
    message = models.TextField()
    triggered_at = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_alert_type_display()} for {self.contract.contract_number}"
