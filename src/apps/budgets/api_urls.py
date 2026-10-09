from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import Budget, SpendLedger


class BudgetSerializer(serializers.ModelSerializer):
    available_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    cost_center_code = serializers.CharField(source="cost_center.code", read_only=True)

    class Meta:
        model = Budget
        fields = "__all__"


class SpendLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpendLedger
        fields = "__all__"


class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.select_related("cost_center", "fiscal_period").all()
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]


class SpendLedgerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SpendLedger.objects.select_related("budget").order_by("-created_at")
    serializer_class = SpendLedgerSerializer
    permission_classes = [IsAuthenticated]


router = DefaultRouter()
router.register(r"ledger", SpendLedgerViewSet, basename="spend-ledger")
router.register(r"", BudgetViewSet, basename="budget")

urlpatterns = router.urls
