from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "companies"

router = DefaultRouter()
router.register("", views.CompanyViewSet, basename="company")

urlpatterns = [
    path(
        "<slug:slug>/members/",
        views.MemberView.as_view(),
        name="member-list",
    ),
    path(
        "<slug:slug>/members/<uuid:pk>/",
        views.MemberView.as_view(),
        name="member-detail",
    ),
    path("", include(router.urls)),
]
