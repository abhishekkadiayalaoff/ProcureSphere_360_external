from celery import shared_task

from .services import scan_contract_expirations_and_milestones_service


@shared_task(name="contracts.tasks.scan_contract_expirations_and_milestones")
def scan_contract_expirations_and_milestones_task():
    """
    Celery Beat scheduled task scanning active contracts and upcoming milestones.
    """
    alerts_created = scan_contract_expirations_and_milestones_service()
    return f"Contract alert scan completed. {alerts_created} alerts generated."
