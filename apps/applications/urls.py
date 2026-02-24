from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "applications"

router = DefaultRouter()
router.register("", views.ApplicationViewSet, basename="application")

urlpatterns = [
    path(
        "<uuid:pk>/status/",
        views.ApplicationStatusUpdateView.as_view(),
        name="application-status",
    ),
    path("", include(router.urls)),
]
