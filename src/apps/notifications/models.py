from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    TYPE_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    TYPE_BID_DEADLINE = "BID_DEADLINE"
    TYPE_EXCEPTION_RAISED = "EXCEPTION_RAISED"
    TYPE_CONTRACT_EXPIRATION = "CONTRACT_EXPIRATION"
    TYPE_PO_ACKNOWLEDGED = "PO_ACKNOWLEDGED"

    TYPE_CHOICES = [
        (TYPE_APPROVAL_REQUIRED, "Approval Required"),
        (TYPE_BID_DEADLINE, "Bid Window Closing"),
        (TYPE_EXCEPTION_RAISED, "3-Way Match Exception"),
        (TYPE_CONTRACT_EXPIRATION, "Contract Expiration Warning"),
        (TYPE_PO_ACKNOWLEDGED, "PO Acknowledged"),
    ]

    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    target_url = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Notification to {self.recipient.email}: {self.title} [{'READ' if self.is_read else 'UNREAD'}]"
