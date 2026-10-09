from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import Vendor, VendorCategory, VendorDocument


class VendorCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorCategory
        fields = "__all__"


class VendorDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorDocument
        fields = "__all__"


class VendorSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    documents = VendorDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = Vendor
        fields = "__all__"


class VendorViewSet(viewsets.ModelViewSet):
    queryset = (
        Vendor.objects.select_related("category").prefetch_related("documents", "contacts").all()
    )
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Vendor user scoping
        if user.is_vendor and user.vendor_id:
            return self.queryset.filter(id=user.vendor_id)
        return self.queryset


class VendorCategoryViewSet(viewsets.ModelViewSet):
    queryset = VendorCategory.objects.all()
    serializer_class = VendorCategorySerializer
    permission_classes = [IsAuthenticated]


router = DefaultRouter()
router.register(r"categories", VendorCategoryViewSet, basename="vendor-category")
router.register(r"", VendorViewSet, basename="vendor")

urlpatterns = router.urls
