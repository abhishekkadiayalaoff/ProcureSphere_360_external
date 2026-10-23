from django.urls import path

from .manager_views import (
    manager_awards_view,
    manager_dashboard_view,
    manager_notifications_view,
    manager_performance_view,
    manager_pipeline_view,
    manager_pr_aging_view,
    manager_purchase_orders_view,
    manager_sourcing_view,
    manager_spend_view,
    manager_vendor_risk_view,
)

urlpatterns = [
    path("", manager_dashboard_view, name="manager_dashboard"),
    path("pipeline/", manager_pipeline_view, name="manager_pipeline"),
    path("pr-aging/", manager_pr_aging_view, name="manager_pr_aging"),
    path("sourcing/", manager_sourcing_view, name="manager_sourcing"),
    path("awards/", manager_awards_view, name="manager_awards"),
    path("purchase-orders/", manager_purchase_orders_view, name="manager_purchase_orders"),
    path("vendor-risk/", manager_vendor_risk_view, name="manager_vendor_risk"),
    path("spend/", manager_spend_view, name="manager_spend"),
    path("performance/", manager_performance_view, name="manager_performance"),
    path("notifications/", manager_notifications_view, name="manager_notifications"),
]
