from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import PRAttachment, PRLine, PurchaseRequisition


class PRLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PRLine
        fields = "__all__"


class PRAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PRAttachment
        fields = "__all__"


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    lines = PRLineSerializer(many=True, read_only=True)
    attachments = PRAttachmentSerializer(many=True, read_only=True)
    requester_email = serializers.CharField(source="requester.email", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = "__all__"


class PurchaseRequisitionViewSet(viewsets.ModelViewSet):
    queryset = (
        PurchaseRequisition.objects.select_related("requester", "department", "cost_center")
        .prefetch_related("lines", "attachments")
        .all()
    )
    serializer_class = PurchaseRequisitionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.role_code in [
            "SUPER_ADMIN",
            "PROC_EXEC",
            "PROC_MGR",
            "AUDITOR",
        ]:
            return self.queryset
        # Requester / Approver scoped by department
        if user.department_id:
            return self.queryset.filter(department_id=user.department_id)
        return self.queryset.filter(requester=user)


router = DefaultRouter()
router.register(r"", PurchaseRequisitionViewSet, basename="requisition")

urlpatterns = router.urls
