import uuid

from django.db import models


class AuditLog(models.Model):
    """
    Append-only immutable audit trail capturing state changes across ProcureSphere 360.
    """

    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_DELETE = "DELETE"
    ACTION_APPROVE = "APPROVE"
    ACTION_REJECT = "REJECT"
    ACTION_LOGIN = "LOGIN"
    ACTION_EXPORT = "EXPORT"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_APPROVE, "Approve"),
        (ACTION_REJECT, "Reject"),
        (ACTION_LOGIN, "Login"),
        (ACTION_EXPORT, "Export Data"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)

    target_model = models.CharField(max_length=100, db_index=True)
    target_object_id = models.CharField(max_length=100, db_index=True)

    previous_state = models.JSONField(null=True, blank=True)
    new_state = models.JSONField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=100, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        actor_str = self.actor.email if self.actor else "System"
        return f"Audit {self.action} on {self.target_model}:{self.target_object_id} by {actor_str} at {self.timestamp}"

    def save(self, *args, **kwargs):
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionError(
                "AuditLog records are append-only and immutable. Edits are strictly prohibited."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError(
            "AuditLog records are append-only and immutable. Deletions are strictly prohibited."
        )
