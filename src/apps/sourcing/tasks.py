from celery import shared_task

from apps.audit.models import AuditLog
from apps.audit.services import create_audit_log_service

from .services import sync_all_event_windows


@shared_task
def sync_sourcing_bid_windows_task():
    """
    Celery Beat: opens bid windows whose start time has been reached and closes those whose
    deadline has passed (BID_WINDOW -> TECHNICAL_REVIEW). Each transition is audited by the
    service; a run record is written only when something changed, as execution evidence.
    """
    changed = sync_all_event_windows()
    if changed:
        create_audit_log_service(
            actor=None,
            action=AuditLog.ACTION_UPDATE,
            target_model="CeleryTaskRun",
            target_object_id="sync_sourcing_bid_windows_task",
            new_state={"events_transitioned": changed},
        )
    return changed
