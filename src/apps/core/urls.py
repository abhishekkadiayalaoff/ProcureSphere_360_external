from django.urls import path

from .views import (
    HealthAPIView,
    approver_dashboard_view,
    auditor_dashboard_view,
    dashboard_redirect_view,
    finance_dashboard_view,
    health_check_view,
    home_view,
    legal_dashboard_view,
    manager_dashboard_view,
    procurement_dashboard_view,
    requester_dashboard_view,
    stores_dashboard_view,
    superadmin_dashboard_view,
    vendor_dashboard_view,
)

urlpatterns = [
    path("", home_view, name="home"),
    path("dashboard/", dashboard_redirect_view, name="dashboard_redirect"),
    # Role-specific dashboard URLs
    path("requester/", requester_dashboard_view, name="requester_dashboard"),
    path("requester/dashboard/", requester_dashboard_view, name="requester_dashboard_alt"),
    path("approver/", approver_dashboard_view, name="approver_dashboard"),
    path("approver/dashboard/", approver_dashboard_view, name="approver_dashboard_alt"),
    path("procurement/", procurement_dashboard_view, name="procurement_dashboard"),
    path("procurement/dashboard/", procurement_dashboard_view, name="procurement_dashboard_alt"),
    path("finance/", finance_dashboard_view, name="finance_dashboard"),
    path("finance/dashboard/", finance_dashboard_view, name="finance_dashboard_alt"),
    path("stores/", stores_dashboard_view, name="stores_dashboard"),
    path("stores/dashboard/", stores_dashboard_view, name="stores_dashboard_alt"),
    path("legal/", legal_dashboard_view, name="legal_dashboard"),
    path("legal/dashboard/", legal_dashboard_view, name="legal_dashboard_alt"),
    path("audit/", auditor_dashboard_view, name="core_auditor_dashboard_hub"),
    path("audit/dashboard/", auditor_dashboard_view, name="core_auditor_dashboard"),
    path("superadmin/dashboard/", superadmin_dashboard_view, name="superadmin_dashboard"),
    path("manager/dashboard/", manager_dashboard_view, name="manager_dashboard_alt"),
    path("vendor/dashboard/", vendor_dashboard_view, name="vendor_dashboard_alt"),
    path("health/", health_check_view, name="health_check"),
    path("api/v1/health/", HealthAPIView.as_view(), name="api_health_check"),
]
