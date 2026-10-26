from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogListSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(
        source="actor.email", read_only=True, default="System / Automated"
    )
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "actor",
            "actor_email",
            "action",
            "action_display",
            "target_model",
            "target_object_id",
            "ip_address",
            "request_id",
        ]


class AuditLogDetailSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(
        source="actor.email", read_only=True, default="System / Automated"
    )
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "actor",
            "actor_email",
            "action",
            "action_display",
            "target_model",
            "target_object_id",
            "previous_state",
            "new_state",
            "ip_address",
            "request_id",
            "user_agent",
        ]


class AuditFilterParamsSerializer(serializers.Serializer):
    actor_id = serializers.UUIDField(required=False, allow_null=True)
    action = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    target_model = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    target_object_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    request_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class VendorComplianceQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    kyc_status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class ApprovalHistoryQuerySerializer(serializers.Serializer):
    target_model = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    action = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    actor_id = serializers.UUIDField(required=False, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class SourcingActivityQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    event_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class POChangesQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class InvoiceExceptionsQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    exception_type = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class ContractChangesQuerySerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class SecurityEventsQuerySerializer(serializers.Serializer):
    action = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    actor_id = serializers.UUIDField(required=False, allow_null=True)
    search = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    start_date = serializers.DateTimeField(required=False, allow_null=True)
    end_date = serializers.DateTimeField(required=False, allow_null=True)
    limit = serializers.IntegerField(default=50, min_value=1, max_value=200)
    offset = serializers.IntegerField(default=0, min_value=0)


class AuditorExportRequestSerializer(serializers.Serializer):
    export_type = serializers.ChoiceField(
        choices=[
            "audit_logs",
            "vendor_compliance",
            "approval_history",
            "sourcing_activity",
            "po_changes",
            "invoice_exceptions",
            "contract_changes",
            "security_events",
            "lifecycle_trail",
        ],
        default="audit_logs",
    )
    export_format = serializers.ChoiceField(
        choices=["csv", "json", "xlsx"],
        default="csv",
    )
    filters = serializers.DictField(required=False, default=dict)


class TransactionLifecycleQuerySerializer(serializers.Serializer):
    identifier = serializers.CharField(
        required=True, help_text="PR, PO, RFQ, Invoice, Contract, or Vendor number / UUID"
    )
    entity_type = serializers.CharField(required=False, default="AUTO")


class EntityAuditTrailQuerySerializer(serializers.Serializer):
    target_model = serializers.CharField(required=True)
    target_object_id = serializers.CharField(required=True)
