from django.contrib.postgres.search import SearchVector
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Job


@receiver(post_save, sender=Job)
def update_search_vector(sender, instance, **kwargs):
    """Rebuild search_vector after every save."""
    Job.objects.filter(pk=instance.pk).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
        )
    )
