from django.urls import path
from rest_framework.routers import DefaultRouter

from .api_views import (
    AuditLogViewSet,
    auditor_approval_history_api_view,
    auditor_contract_changes_api_view,
    auditor_dashboard_summary_api_view,
    auditor_export_api_view,
    auditor_invoice_exceptions_api_view,
    auditor_lifecycle_api_view,
    auditor_po_changes_api_view,
    auditor_security_events_api_view,
    auditor_sourcing_activity_api_view,
    auditor_vendor_compliance_api_view,
)

router = DefaultRouter()
router.register(r"logs", AuditLogViewSet, basename="audit-log")

urlpatterns = router.urls + [
    path(
        "dashboard-summary/", auditor_dashboard_summary_api_view, name="auditor-dashboard-summary"
    ),
    path("dashboard/", auditor_dashboard_summary_api_view, name="auditor-dashboard"),
    path(
        "vendor-compliance/", auditor_vendor_compliance_api_view, name="auditor-vendor-compliance"
    ),
    path("approval-history/", auditor_approval_history_api_view, name="auditor-approval-history"),
    path("approvals/", auditor_approval_history_api_view, name="auditor-approvals"),
    path(
        "sourcing-activity/", auditor_sourcing_activity_api_view, name="auditor-sourcing-activity"
    ),
    path("sourcing/", auditor_sourcing_activity_api_view, name="auditor-sourcing"),
    path("po-changes/", auditor_po_changes_api_view, name="auditor-po-changes"),
    path(
        "invoice-exceptions/",
        auditor_invoice_exceptions_api_view,
        name="auditor-invoice-exceptions",
    ),
    path("contract-changes/", auditor_contract_changes_api_view, name="auditor-contract-changes"),
    path("security-events/", auditor_security_events_api_view, name="auditor-security-events"),
    path("lifecycle/", auditor_lifecycle_api_view, name="auditor-lifecycle"),
    path("export/", auditor_export_api_view, name="auditor-export"),
]
