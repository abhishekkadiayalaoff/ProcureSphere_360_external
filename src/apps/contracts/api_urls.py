from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import Contract, ContractAlert, ContractMilestone


class ContractMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractMilestone
        fields = "__all__"


class ContractAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractAlert
        fields = "__all__"


class ContractSerializer(serializers.ModelSerializer):
    milestones = ContractMilestoneSerializer(many=True, read_only=True)
    alerts = ContractAlertSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)

    class Meta:
        model = Contract
        fields = "__all__"


class ContractViewSet(viewsets.ModelViewSet):
    queryset = (
        Contract.objects.select_related("vendor", "contract_owner")
        .prefetch_related("milestones", "alerts")
        .all()
    )
    serializer_class = ContractSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_vendor and user.vendor_id:
            return self.queryset.filter(vendor_id=user.vendor_id)
        return self.queryset


router = DefaultRouter()
router.register(r"", ContractViewSet, basename="contract")

urlpatterns = router.urls
