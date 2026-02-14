from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import models
from django.utils import timezone


class JobManager(models.Manager):
    def published(self):
        """Return only published, non-expired jobs."""
        today = timezone.now().date()
        return (
            self.get_queryset()
            .filter(status="published")
            .exclude(deadline__lt=today)
        )

    def search(self, query):
        """Full-text search across published jobs using PostgreSQL tsvector."""
        search_query = SearchQuery(query)
        return (
            self.published()
            .filter(search_vector=search_query)
            .annotate(rank=SearchRank("search_vector", search_query))
            .filter(rank__gt=0)
            .order_by("-rank")
        )

    def with_application_count(self):
        """Annotate published jobs with application count."""
        return self.published().annotate(
            application_count=models.Count("applications")
        )
