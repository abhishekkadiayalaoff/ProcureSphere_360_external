from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import GoodsReceipt, ReceiptLine


class ReceiptLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptLine
        fields = "__all__"


class GoodsReceiptSerializer(serializers.ModelSerializer):
    lines = ReceiptLineSerializer(many=True, read_only=True)
    po_number = serializers.CharField(source="po.po_number", read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = "__all__"


class GoodsReceiptViewSet(viewsets.ModelViewSet):
    queryset = (
        GoodsReceipt.objects.select_related("po", "received_by").prefetch_related("lines").all()
    )
    serializer_class = GoodsReceiptSerializer
    permission_classes = [IsAuthenticated]


router = DefaultRouter()
router.register(r"", GoodsReceiptViewSet, basename="goods-receipt")

urlpatterns = router.urls
