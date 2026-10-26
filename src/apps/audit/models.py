import uuid

from django.db import models


class AuditLog(models.Model):
    """
    Append-only immutable audit trail capturing state changes across ProcureSphere 360.
    Enforces strict immutability by preventing modifications and deletions.
    """

    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_DELETE = "DELETE"
    ACTION_APPROVE = "APPROVE"
    ACTION_REJECT = "REJECT"
    ACTION_LOGIN = "LOGIN"
    ACTION_LOGOUT = "LOGOUT"
    ACTION_EXPORT = "EXPORT"
    ACTION_AMEND = "AMEND"
    ACTION_SUBMIT = "SUBMIT"
    ACTION_CANCEL = "CANCEL"
    ACTION_OVERRIDE = "OVERRIDE"
    ACTION_ACKNOWLEDGE = "ACKNOWLEDGE"
    ACTION_VERIFY = "VERIFY"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_APPROVE, "Approve"),
        (ACTION_REJECT, "Reject"),
        (ACTION_LOGIN, "Login"),
        (ACTION_LOGOUT, "Logout"),
        (ACTION_EXPORT, "Export Data"),
        (ACTION_AMEND, "Amend / Version"),
        (ACTION_SUBMIT, "Submit for Approval"),
        (ACTION_CANCEL, "Cancel"),
        (ACTION_OVERRIDE, "Override Exception"),
        (ACTION_ACKNOWLEDGE, "Acknowledge"),
        (ACTION_VERIFY, "Verify KYC / Compliance"),
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
    request_id = models.CharField(max_length=100, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["target_model", "target_object_id"], name="audit_target_idx"),
            models.Index(fields=["timestamp", "action"], name="audit_ts_action_idx"),
            models.Index(fields=["actor", "timestamp"], name="audit_actor_ts_idx"),
            models.Index(fields=["request_id"], name="audit_req_id_idx"),
        ]

    @property
    def created_at(self):
        return self.timestamp

    @property
    def entity_name(self):
        return self.target_model

    @property
    def entity_id(self):
        return self.target_object_id

    @property
    def changes_summary(self):
        if self.new_state:
            return str(self.new_state)
        if self.previous_state:
            return str(self.previous_state)
        return ""

    def __str__(self):
        actor_str = self.actor.email if self.actor else "System"
        return f"Audit {self.action} on {self.target_model}:{self.target_object_id} by {actor_str} at {self.timestamp}"

    @property
    def readable_target(self):
        from django.apps import apps

        try:
            for app_config in apps.get_app_configs():
                try:
                    model = app_config.get_model(self.target_model)
                    obj = model.objects.get(pk=self.target_object_id)
                    return f"{self.target_model} {str(obj)}"
                except LookupError:
                    continue
                except model.DoesNotExist:
                    break
        except Exception:
            pass

        # Fallback: model name + first 8 characters of UUID
        short_id = str(self.target_object_id)[:8]
        return f"{self.target_model} #{short_id}"

    @property
    def actor_email(self):
        return self.actor.email if self.actor else "System / Automated"

    @property
    def actor_role(self):
        if self.actor and hasattr(self.actor, "role_code") and self.actor.role_code:
            return self.actor.role_code
        return "SYSTEM"

    @property
    def summary(self):
        if self.new_state and isinstance(self.new_state, dict):
            status = self.new_state.get("status")
            if status:
                return f"Status transitioned to {status}"
            title = (
                self.new_state.get("title")
                or self.new_state.get("legal_name")
                or self.new_state.get("number")
            )
            if title:
                return f"{self.action} on {title}"
        return f"{self.get_action_display()} on {self.target_model}"

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
