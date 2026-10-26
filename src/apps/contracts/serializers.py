from rest_framework import serializers

from .models import (
    Contract,
    ContractAlert,
    ContractDocument,
    ContractMilestone,
    ContractObligation,
    ContractVersion,
)


class ContractVersionSerializer(serializers.ModelSerializer):
    approved_by_email = serializers.CharField(source="approved_by.email", read_only=True)

    class Meta:
        model = ContractVersion
        fields = "__all__"


class ContractMilestoneSerializer(serializers.ModelSerializer):
    due_status = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()

    class Meta:
        model = ContractMilestone
        fields = "__all__"


class ContractObligationSerializer(serializers.ModelSerializer):
    due_status = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    days_remaining = serializers.ReadOnlyField()

    class Meta:
        model = ContractObligation
        fields = "__all__"


class ContractDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.CharField(source="uploaded_by.email", read_only=True)

    class Meta:
        model = ContractDocument
        fields = "__all__"


class ContractAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractAlert
        fields = "__all__"


class ContractSerializer(serializers.ModelSerializer):
    milestones = ContractMilestoneSerializer(many=True, read_only=True)
    obligations = ContractObligationSerializer(many=True, read_only=True)
    documents = ContractDocumentSerializer(many=True, read_only=True)
    versions = ContractVersionSerializer(many=True, read_only=True)
    alerts = ContractAlertSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)
    owner_email = serializers.CharField(source="contract_owner.email", read_only=True)

    class Meta:
        model = Contract
        fields = "__all__"
        read_only_fields = (
            "contract_number",
            "status",
            "version",
            "created_at",
            "updated_at",
            "contract_owner",
        )
