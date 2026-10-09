from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.routers import DefaultRouter

from .models import ApprovalAction, ApprovalPolicy


class ApprovalPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalPolicy
        fields = "__all__"


class ApprovalActionSerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(source="actor.email", read_only=True)

    class Meta:
        model = ApprovalAction
        fields = "__all__"


class ApprovalPolicyViewSet(viewsets.ModelViewSet):
    queryset = ApprovalPolicy.objects.all()
    serializer_class = ApprovalPolicySerializer
    permission_classes = [IsAuthenticated]


class ApprovalActionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApprovalAction.objects.select_related("actor", "policy_step").order_by("-created_at")
    serializer_class = ApprovalActionSerializer
    permission_classes = [IsAuthenticated]


router = DefaultRouter()
router.register(r"policies", ApprovalPolicyViewSet, basename="approval-policy")
router.register(r"actions", ApprovalActionViewSet, basename="approval-action")

urlpatterns = router.urls
