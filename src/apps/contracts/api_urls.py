from rest_framework.routers import DefaultRouter

from .api_views import ContractViewSet

router = DefaultRouter()
router.register(r"", ContractViewSet, basename="contract")

urlpatterns = router.urls
