import django_filters

from .models import Job


class JobFilter(django_filters.FilterSet):
    title = django_filters.CharFilter(lookup_expr="icontains")
    location = django_filters.CharFilter(lookup_expr="icontains")
    salary_min = django_filters.NumberFilter(field_name="salary_min", lookup_expr="gte")
    salary_max = django_filters.NumberFilter(field_name="salary_max", lookup_expr="lte")
    is_remote = django_filters.BooleanFilter()
    job_type = django_filters.MultipleChoiceFilter(choices=Job.JobType.choices)
    experience_level = django_filters.MultipleChoiceFilter(choices=Job.ExperienceLevel.choices)
    company = django_filters.UUIDFilter(field_name="company_id")

    class Meta:
        model = Job
        fields = [
            "title",
            "location",
            "salary_min",
            "salary_max",
            "is_remote",
            "job_type",
            "experience_level",
            "company",
        ]
