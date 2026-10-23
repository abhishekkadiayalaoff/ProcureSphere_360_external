from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "actor",
        "action",
        "target_model",
        "target_object_id",
        "ip_address",
        "request_id",
    )
    list_filter = ("action", "target_model", "timestamp")
    search_fields = (
        "actor__email",
        "target_model",
        "target_object_id",
        "request_id",
    )
    readonly_fields = (
        "id",
        "timestamp",
        "actor",
        "action",
        "target_model",
        "target_object_id",
        "previous_state",
        "new_state",
        "ip_address",
        "request_id",
        "user_agent",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
