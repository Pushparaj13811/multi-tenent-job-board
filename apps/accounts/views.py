from django.core.signing import BadSignature, SignatureExpired
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView as BaseTokenRefreshView

from .models import User
from .serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
    UserUpdateSerializer,
    VerifyEmailSerializer,
)
from .tokens import verify_email_token


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — Create a new user account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/ — Obtain JWT access and refresh tokens."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {
                    "error": "No active account found with the given credentials.",
                    "code": "authentication_failed",
                    "details": {},
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(BaseTokenRefreshView):
    """POST /api/auth/token/refresh/ — Refresh an access token."""

    permission_classes = [AllowAny]
    authentication_classes = []


class VerifyEmailView(APIView):
    """POST /api/auth/verify-email/ — Verify email via signed token."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["token"]

        try:
            user_id = verify_email_token(token)
        except (BadSignature, SignatureExpired):
            return Response(
                {"error": "Token is invalid or expired.", "code": "invalid_token", "details": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "User not found.", "code": "user_not_found", "details": {}},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified", "updated_at"])

        return Response(
            {"detail": "Email verified successfully.", "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class CurrentUserView(APIView):
    """GET/PATCH /api/auth/me/ — View or update own profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ — Change own password."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "updated_at"])
        return Response({"detail": "Password changed successfully."})


class AvatarUploadView(APIView):
    """POST /api/auth/avatar/ — Upload profile avatar."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.avatar = serializer.validated_data["avatar"]
        request.user.save(update_fields=["avatar", "updated_at"])
        return Response(UserSerializer(request.user).data)
