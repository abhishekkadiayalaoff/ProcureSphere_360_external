from rest_framework.routers import DefaultRouter

from .api_views import RoleViewSet, UserViewSet

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"roles", RoleViewSet, basename="role")

urlpatterns = router.urls
