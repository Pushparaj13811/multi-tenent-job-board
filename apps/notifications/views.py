from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(ListModelMixin, GenericViewSet):
    """List, mark-read, and mark-all-read for the authenticated user's notifications."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == "true")
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        unread_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        response.data["unread_count"] = unread_count
        return response

    @action(detail=True, methods=["patch"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        count = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True)
        return Response({"marked_read": count}, status=status.HTTP_200_OK)
