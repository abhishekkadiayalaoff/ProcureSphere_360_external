from django.urls import path

from .views import (
    audit_approvals_view,
    audit_contract_changes_view,
    audit_invoice_exceptions_view,
    audit_lifecycle_view,
    audit_log_view,
    audit_metrics_api_view,
    audit_po_changes_view,
    audit_security_events_view,
    audit_sourcing_activity_view,
    audit_vendors_view,
    auditor_dashboard_view,
)

urlpatterns = [
    # Main Executive Dashboard
    path("audit/", auditor_dashboard_view, name="auditor_dashboard_hub"),
    path("audit/dashboard/", auditor_dashboard_view, name="auditor_dashboard"),
    path("auditor/", auditor_dashboard_view, name="auditor_portal_hub"),
    path("auditor/dashboard/", auditor_dashboard_view, name="auditor_portal_dashboard"),
    # Dedicated Sub-Module Pages
    path("audit/logs/", audit_log_view, name="audit_log"),
    path("auditor/logs/", audit_log_view, name="auditor_logs"),
    path("audit/vendors/", audit_vendors_view, name="audit_vendors"),
    path("auditor/vendors/", audit_vendors_view, name="auditor_vendors"),
    path("audit/approvals/", audit_approvals_view, name="audit_approvals"),
    path("auditor/approvals/", audit_approvals_view, name="auditor_approvals"),
    path("audit/po-changes/", audit_po_changes_view, name="audit_po_changes"),
    path("auditor/po-changes/", audit_po_changes_view, name="auditor_po_changes"),
    path(
        "audit/invoice-exceptions/", audit_invoice_exceptions_view, name="audit_invoice_exceptions"
    ),
    path(
        "auditor/invoice-exceptions/",
        audit_invoice_exceptions_view,
        name="auditor_invoice_exceptions",
    ),
    path("audit/contract-changes/", audit_contract_changes_view, name="audit_contract_changes"),
    path("auditor/contract-changes/", audit_contract_changes_view, name="auditor_contract_changes"),
    path("audit/security-events/", audit_security_events_view, name="audit_security_events"),
    path("auditor/security-events/", audit_security_events_view, name="auditor_security_events"),
    path("audit/sourcing-activity/", audit_sourcing_activity_view, name="audit_sourcing_activity"),
    path(
        "auditor/sourcing-activity/", audit_sourcing_activity_view, name="auditor_sourcing_activity"
    ),
    path("audit/lifecycle/", audit_lifecycle_view, name="audit_lifecycle"),
    path("auditor/lifecycle/", audit_lifecycle_view, name="auditor_lifecycle"),
    path("audit/metrics/", audit_metrics_api_view, name="audit_metrics"),
    path("auditor/metrics/", audit_metrics_api_view, name="auditor_metrics"),
]
