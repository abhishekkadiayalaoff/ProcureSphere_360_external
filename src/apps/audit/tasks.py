from celery import shared_task

from .services import export_auditor_data_service


@shared_task(name="apps.audit.tasks.generate_auditor_export_task")
def generate_auditor_export_task(
    export_type: str,
    export_format: str = "csv",
    filters: dict = None,
    actor_id: str = None,
):
    from apps.accounts.models import User

    actor = User.objects.filter(id=actor_id).first() if actor_id else None
    result = export_auditor_data_service(
        export_type=export_type,
        export_format=export_format,
        filters=filters or {},
        actor=actor,
    )
    return {
        "export_ref_id": result["export_ref_id"],
        "checksum": result["checksum"],
        "algorithm": result["algorithm"],
        "filename": result["filename"],
        "record_count": result["record_count"],
        "status": "COMPLETED",
    }
