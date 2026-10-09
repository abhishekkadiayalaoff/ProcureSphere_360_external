import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def test_celery_worker_task(message="Hello from Celery Worker!"):
    """A dummy task to verify the celery worker is picking up jobs."""
    logger.info(f"Worker Task Executed at {timezone.now()}: {message}")
    print(f"Worker Task Executed at {timezone.now()}: {message}")
    return f"Success: {message}"


@shared_task
def test_celery_beat_task():
    """A dummy task to verify celery beat is scheduling periodic jobs."""
    logger.info(f"Beat Task Triggered at {timezone.now()}")
    print(f"Beat Task Triggered at {timezone.now()}")
    return "Beat Triggered Successfully"
