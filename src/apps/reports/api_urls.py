from django.urls import path
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter

from .models import ExportJob
from .services import (
    generate_export_job_service,
    get_audit_log_report,
    get_contract_expiry_report,
    get_invoice_exception_aging_report,
    get_po_status_report,
    get_pr_aging_report,
    get_receipt_rejection_report,
    get_sourcing_cycle_time_report,
    get_spend_analytics_report,
    get_supplier_performance_report,
)


class ExportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportJob
        fields = "__all__"


class ExportJobViewSet(viewsets.ModelViewSet):
    queryset = ExportJob.objects.select_related("requested_by").order_by("-created_at")
    serializer_class = ExportJobSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        job = serializer.save(requested_by=self.request.user)
        generate_export_job_service(job.id)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary_view(request):
    """
    Executes executive procurement dashboard overview combining spend, PRs, POs, Invoices, Contracts.
    """
    pr_data = get_pr_aging_report()
    spend_data = get_spend_analytics_report()
    po_data = get_po_status_report()
    inv_data = get_invoice_exception_aging_report()
    contract_data = get_contract_expiry_report()
    scorecard_data = get_supplier_performance_report()

    summary = {
        "total_prs": len(pr_data),
        "total_pos": len(po_data),
        "total_spend": sum(item["actual"] for item in spend_data),
        "pending_exceptions": len([item for item in inv_data if item["status"] == "OPEN"]),
        "expiring_contracts": len(
            [item for item in contract_data if 0 <= item["days_to_expiry"] <= 60]
        ),
        "vendor_count": len(scorecard_data),
    }
    return Response(summary, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pr_aging_report_view(request):
    return Response(get_pr_aging_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def spend_analytics_report_view(request):
    return Response(get_spend_analytics_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sourcing_cycle_report_view(request):
    return Response(get_sourcing_cycle_time_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def po_status_report_view(request):
    return Response(get_po_status_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def receipt_rejection_report_view(request):
    return Response(get_receipt_rejection_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def invoice_exception_report_view(request):
    return Response(get_invoice_exception_aging_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def contract_expiry_report_view(request):
    return Response(get_contract_expiry_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def supplier_performance_report_view(request):
    return Response(get_supplier_performance_report(), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_log_report_view(request):
    return Response(get_audit_log_report(), status=status.HTTP_200_OK)


router = DefaultRouter()

router.register(r"exports", ExportJobViewSet, basename="export-job")

urlpatterns = router.urls + [
    path("dashboard-summary/", dashboard_summary_view, name="dashboard-summary"),
    path("pr-aging/", pr_aging_report_view, name="report-pr-aging"),
    path("spend-analytics/", spend_analytics_report_view, name="report-spend-analytics"),
    path("sourcing-cycle/", sourcing_cycle_report_view, name="report-sourcing-cycle"),
    path("po-status/", po_status_report_view, name="report-po-status"),
    path("receipt-rejection/", receipt_rejection_report_view, name="report-receipt-rejection"),
    path("invoice-exceptions/", invoice_exception_report_view, name="report-invoice-exceptions"),
    path("contract-expiry/", contract_expiry_report_view, name="report-contract-expiry"),
    path(
        "supplier-performance/",
        supplier_performance_report_view,
        name="report-supplier-performance",
    ),
    path("audit-logs/", audit_log_report_view, name="report-audit-logs"),
]
