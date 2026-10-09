from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import POAmendment, POLine, PurchaseOrder


class POLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = POLine
        fields = "__all__"


class POAmendmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = POAmendment
        fields = "__all__"


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = POLineSerializer(many=True, read_only=True)
    amendments = POAmendmentSerializer(many=True, read_only=True)
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = "__all__"


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = (
        PurchaseOrder.objects.select_related("vendor", "cost_center")
        .prefetch_related("lines", "amendments")
        .all()
    )
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_vendor and user.vendor_id:
            return self.queryset.filter(vendor_id=user.vendor_id)
        return self.queryset


router = DefaultRouter()
router.register(r"", PurchaseOrderViewSet, basename="purchase-order")

urlpatterns = router.urls
