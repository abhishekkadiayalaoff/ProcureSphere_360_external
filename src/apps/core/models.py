import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """
    Abstract base model providing self-updating created_at and updated_at fields.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )

    class Meta:
        abstract = True


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract base model for entities requiring non-destructive soft-deletion.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(class)s_deleted",
    )

    class Meta:
        abstract = True

class ContactEnquiry(TimeStampedModel):
    """
    Stores contact and demo enquiries submitted from the public landing website.
    Visible and manageable by staff/superadmins in the Django admin portal.
    """

    STATUS_NEW = "NEW"
    STATUS_IN_REVIEW = "IN_REVIEW"
    STATUS_CONTACTED = "CONTACTED"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_SPAM = "SPAM"

    STATUS_CHOICES = (
        (STATUS_NEW, "New"),
        (STATUS_IN_REVIEW, "In Review"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_SPAM, "Spam"),
    )

    name = models.CharField(max_length=60, help_text="Full name of the contact person")
    email = models.EmailField(max_length=255, help_text="Contact email address")
    country_code = models.CharField(max_length=10, default="+91", help_text="Country dial code (e.g. +91, +1)")
    phone = models.CharField(max_length=20, help_text="Mobile / phone number")
    message = models.TextField(help_text="Enquiry message or requirements")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
        help_text="Current triage status of the enquiry",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="Client IP address of submitter")
    user_agent = models.CharField(max_length=500, blank=True, default="", help_text="Client User-Agent header")
    notes = models.TextField(blank=True, default="", help_text="Internal staff follow-up notes")

    class Meta:
        verbose_name = "Contact Enquiry"
        verbose_name_plural = "Contact Enquiries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="core_enq_status_idx"),
            models.Index(fields=["email"], name="core_enq_email_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.email}) - {self.get_status_display()}"

    @property
    def formatted_phone(self):
        return f"{self.country_code} {self.phone}".strip()

