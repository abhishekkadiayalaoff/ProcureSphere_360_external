from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import SourcingEvent, VendorBid


class SourcingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourcingEvent
        fields = "__all__"


class VendorBidSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.legal_name", read_only=True)

    class Meta:
        model = VendorBid
        fields = "__all__"


class SourcingEventViewSet(viewsets.ModelViewSet):
    queryset = SourcingEvent.objects.prefetch_related("invitations", "bids").all()
    serializer_class = SourcingEventSerializer
    permission_classes = [IsAuthenticated]


class VendorBidViewSet(viewsets.ModelViewSet):
    queryset = VendorBid.objects.select_related("event", "vendor").prefetch_related("lines").all()
    serializer_class = VendorBidSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Vendor sealed bid scoping: vendors see only their own bids
        if user.is_vendor and user.vendor_id:
            return self.queryset.filter(vendor_id=user.vendor_id)
        return self.queryset


router = DefaultRouter()
router.register(r"events", SourcingEventViewSet, basename="sourcing-event")
router.register(r"bids", VendorBidViewSet, basename="vendor-bid")

urlpatterns = router.urls
