from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from apps.accounts.permissions import IsAuditorReadOnly, IsSuperAdmin

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(source="actor.email", read_only=True, default="System")

    class Meta:
        model = AuditLog
        fields = "__all__"


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsAuditorReadOnly | IsSuperAdmin]


router = DefaultRouter()
router.register(r"logs", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls
