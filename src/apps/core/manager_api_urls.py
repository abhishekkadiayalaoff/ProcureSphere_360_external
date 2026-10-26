from django.urls import path

from .manager_api_views import (
    ManagerKPIsAPIView,
    ManagerPerformanceSummaryAPIView,
    ManagerPipelineAPIView,
    ManagerPRAgingAPIView,
    ManagerSpendAnalyticsAPIView,
    ManagerSpendExportAPIView,
    ManagerSpendSummaryAPIView,
    ManagerSupplierCompareAPIView,
    ManagerSupplierPerformanceAPIView,
    ManagerSupplierPerformanceDetailAPIView,
)

urlpatterns = [
    path("kpis/", ManagerKPIsAPIView.as_view(), name="manager-kpis-api"),
    path("pipeline/", ManagerPipelineAPIView.as_view(), name="manager-pipeline-api"),
    path("pr-aging/", ManagerPRAgingAPIView.as_view(), name="manager-pr-aging-api"),
    # Spend Analytics
    path("spend/", ManagerSpendAnalyticsAPIView.as_view(), name="manager-spend-api"),
    path("spend/summary/", ManagerSpendSummaryAPIView.as_view(), name="manager-spend-summary-api"),
    path("spend/export/", ManagerSpendExportAPIView.as_view(), name="manager-spend-export-api"),
    # Supplier Performance
    path(
        "performance/", ManagerSupplierPerformanceAPIView.as_view(), name="manager-performance-api"
    ),
    path(
        "performance/summary/",
        ManagerPerformanceSummaryAPIView.as_view(),
        name="manager-performance-summary-api",
    ),
    path(
        "performance/compare/",
        ManagerSupplierCompareAPIView.as_view(),
        name="manager-performance-compare-api",
    ),
    path(
        "performance/<uuid:vendor_id>/",
        ManagerSupplierPerformanceDetailAPIView.as_view(),
        name="manager-performance-detail-api",
    ),
]
