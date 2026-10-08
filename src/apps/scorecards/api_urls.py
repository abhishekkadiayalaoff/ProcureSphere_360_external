from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from apps.vendors.models import Vendor

from .models import VendorScorecard
from .services import calculate_vendor_scorecard_service


class VendorScorecardSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)

    class Meta:
        model = VendorScorecard
        fields = "__all__"


class VendorScorecardViewSet(viewsets.ModelViewSet):
    queryset = VendorScorecard.objects.select_related("vendor", "evaluated_by").all()
    serializer_class = VendorScorecardSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_vendor and user.vendor_id:
            return self.queryset.filter(vendor_id=user.vendor_id)
        return self.queryset

    @action(detail=False, methods=["post"], url_path="calculate")
    def calculate(self, request):
        vendor_id = request.data.get("vendor_id")
        period = request.data.get("period", "Q1-2026")
        comments = request.data.get("comments", "")

        if not vendor_id:
            return Response({"error": "vendor_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        vendor = Vendor.objects.get(pk=vendor_id)
        scorecard = calculate_vendor_scorecard_service(
            vendor=vendor,
            evaluation_period=period,
            evaluated_by_user=request.user,
            comments=comments,
        )
        return Response(VendorScorecardSerializer(scorecard).data, status=status.HTTP_201_CREATED)


router = DefaultRouter()
router.register(r"", VendorScorecardViewSet, basename="scorecard")

urlpatterns = router.urls
