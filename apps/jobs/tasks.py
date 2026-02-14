from django.utils import timezone

from celery import shared_task


@shared_task
def close_expired_jobs():
    """Periodic task — runs daily via Celery Beat. Closes published jobs past deadline."""
    from apps.jobs.models import Job

    expired = Job.objects.filter(
        status=Job.Status.PUBLISHED,
        deadline__lt=timezone.now().date(),
    )
    count = expired.update(status=Job.Status.CLOSED)
    return f"Closed {count} expired jobs."
