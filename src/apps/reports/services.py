import csv
import io

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.budgets.models import Budget
from apps.contracts.models import Contract
from apps.invoices.models import MatchException
from apps.orders.models import PurchaseOrder
from apps.receipts.models import ReceiptLine
from apps.requisitions.models import PurchaseRequisition
from apps.scorecards.models import VendorScorecard
from apps.sourcing.models import SourcingEvent

from .models import ExportJob


def get_pr_aging_report():
    """1. PR aging and approval-bottleneck report"""
    prs = PurchaseRequisition.objects.select_related("requester", "department", "cost_center").all()
    now = timezone.now()
    report_data = []
    for pr in prs:
        age_days = (now - pr.created_at).days
        report_data.append(
            {
                "pr_number": pr.pr_number,
                "title": pr.title,
                "department": pr.department.name if pr.department else "N/A",
                "cost_center": pr.cost_center.code if pr.cost_center else "N/A",
                "status": pr.status,
                "total_amount": float(pr.total_amount),
                "created_at": pr.created_at.strftime("%Y-%m-%d"),
                "age_days": age_days,
            }
        )
    return report_data


def get_spend_analytics_report():
    """2. Spend by vendor / category / department / cost center / period"""
    budgets = Budget.objects.select_related("cost_center", "fiscal_period").all()
    report_data = []
    for b in budgets:
        report_data.append(
            {
                "cost_center": b.cost_center.code,
                "cost_center_name": b.cost_center.name,
                "fiscal_period": b.fiscal_period.name,
                "allocated": float(b.allocated_amount),
                "reserved": float(b.reserved_amount),
                "committed": float(b.committed_amount),
                "actual": float(b.actual_amount),
                "available": float(b.available_amount),
            }
        )
    return report_data


def get_sourcing_cycle_time_report():
    """3. Sourcing cycle time and bid participation"""
    events = SourcingEvent.objects.prefetch_related("bids", "invitations").all()
    report_data = []
    for e in events:
        bid_count = e.bids.count()
        invite_count = e.invitations.count()
        report_data.append(
            {
                "event_number": e.event_number,
                "title": e.title,
                "event_type": e.event_type,
                "status": e.status,
                "invited_vendors": invite_count,
                "submitted_bids": bid_count,
                "start_date": str(e.start_date),
                "end_date": str(e.end_date),
            }
        )
    return report_data


def get_po_status_report():
    """4. PO open / partial / closed status"""
    pos = PurchaseOrder.objects.select_related("vendor", "cost_center").all()
    report_data = []
    for po in pos:
        report_data.append(
            {
                "po_number": po.po_number,
                "version": po.version,
                "vendor": po.vendor.legal_name,
                "cost_center": po.cost_center.code,
                "status": po.status,
                "total_amount": float(po.total_amount),
                "acknowledged_at": str(po.acknowledged_at) if po.acknowledged_at else None,
            }
        )
    return report_data


def get_receipt_rejection_report():
    """5. Receipt / rejection and delivery performance"""
    receipt_lines = ReceiptLine.objects.select_related("receipt__po__vendor", "po_line").all()
    report_data = []
    for rl in receipt_lines:
        report_data.append(
            {
                "grn_number": rl.receipt.grn_number,
                "po_number": rl.receipt.po.po_number,
                "vendor": rl.receipt.po.vendor.legal_name,
                "received_date": rl.receipt.received_date.strftime("%Y-%m-%d"),
                "qty_received": float(rl.quantity_received),
                "qty_accepted": float(rl.quantity_accepted),
                "qty_rejected": float(rl.quantity_rejected),
            }
        )
    return report_data


def get_invoice_exception_aging_report():
    """6. Invoice match-exception aging"""
    exceptions = MatchException.objects.select_related("invoice__vendor", "resolved_by").all()
    now = timezone.now()
    report_data = []
    for exc in exceptions:
        age_days = (now - exc.created_at).days
        report_data.append(
            {
                "invoice_number": exc.invoice.invoice_number,
                "vendor": exc.invoice.vendor.legal_name,
                "exception_type": exc.exception_type,
                "status": exc.status,
                "variance_amount": float(exc.variance_amount),
                "age_days": age_days,
                "resolved_by": exc.resolved_by.email if exc.resolved_by else None,
            }
        )
    return report_data


def get_contract_expiry_report():
    """7. Contract expiry / renewal / obligation"""
    contracts = Contract.objects.select_related("vendor").all()
    now = timezone.now().date()
    report_data = []
    for c in contracts:
        days_to_expiry = (c.end_date - now).days if c.end_date else 0
        report_data.append(
            {
                "contract_number": c.contract_number,
                "title": c.title,
                "vendor": c.vendor.legal_name,
                "contract_type": c.contract_type,
                "status": c.status,
                "total_value": float(c.total_value),
                "end_date": str(c.end_date),
                "days_to_expiry": days_to_expiry,
            }
        )
    return report_data


def get_supplier_performance_report():
    """8. Supplier performance scorecard and trend"""
    scorecards = VendorScorecard.objects.select_related("vendor", "evaluated_by").all()
    report_data = []
    for sc in scorecards:
        report_data.append(
            {
                "vendor": sc.vendor.legal_name,
                "period": sc.evaluation_period,
                "delivery_score": float(sc.delivery_score),
                "quality_score": float(sc.quality_score),
                "price_score": float(sc.price_score),
                "compliance_score": float(sc.compliance_score),
                "composite_score": float(sc.composite_score),
                "evaluated_by": sc.evaluated_by.email,
            }
        )
    return report_data


def get_audit_log_report():
    """9. User / approval audit export with filters and immutable references"""
    logs = AuditLog.objects.select_related("actor").all()[:200]
    report_data = []
    for log in logs:
        report_data.append(
            {
                "audit_id": str(log.id),
                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "actor": log.actor.email if log.actor else "System",
                "action": log.action,
                "target_model": log.target_model,
                "target_object_id": log.target_object_id,
            }
        )
    return report_data


REPORT_DISPATCHER = {
    "pr_aging": get_pr_aging_report,
    "spend_analytics": get_spend_analytics_report,
    "sourcing_cycle_time": get_sourcing_cycle_time_report,
    "po_status": get_po_status_report,
    "receipt_rejection": get_receipt_rejection_report,
    "invoice_exception_aging": get_invoice_exception_aging_report,
    "contract_expiry": get_contract_expiry_report,
    "supplier_performance": get_supplier_performance_report,
    "audit_log": get_audit_log_report,
}


def generate_export_job_service(export_job_id: int) -> ExportJob:
    """
    Processes an ExportJob, generates CSV file, attaches result file, and logs audit event.
    """
    job = ExportJob.objects.get(pk=export_job_id)
    job.status = ExportJob.STATUS_PROCESSING
    job.save(update_fields=["status", "updated_at"])

    try:
        report_fn = REPORT_DISPATCHER.get(job.report_type, get_audit_log_report)
        data = report_fn()

        output = io.StringIO()
        if data:
            fieldnames = list(data[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
        else:
            output.write("No data available for export.\n")

        filename = f"{job.report_type}_export_{job.id}.csv"
        job.result_file.save(filename, ContentFile(output.getvalue().encode("utf-8")), save=False)
        job.status = ExportJob.STATUS_COMPLETED
        job.save(update_fields=["status", "result_file", "updated_at"])

        AuditLog.objects.create(
            actor=job.requested_by,
            action=AuditLog.ACTION_EXPORT,
            target_model="ExportJob",
            target_object_id=str(job.id),
            new_state={
                "report_type": job.report_type,
                "format": job.export_format,
                "record_count": len(data),
            },
        )
    except Exception as e:
        job.status = ExportJob.STATUS_FAILED
        job.error_message = str(e)
        job.save(update_fields=["status", "error_message", "updated_at"])
        raise e

    return job
