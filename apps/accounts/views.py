from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import User, APIToken
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    UserUpdateSerializer,
    APITokenSerializer,
    APITokenCreateSerializer,
    get_tokens_for_user,
)


class RegisterView(APIView):
    """POST /api/auth/register/ — Create a new user account."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        tokens = get_tokens_for_user(user)

        return Response({
            'user': UserSerializer(user).data,
            'access': tokens['access'],
            'refresh': tokens['refresh'],
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/ — Authenticate and receive JWT tokens."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']
        tokens = get_tokens_for_user(user)

        return Response({
            'user': UserSerializer(user).data,
            'access': tokens['access'],
            'refresh': tokens['refresh'],
        })


class RefreshView(APIView):
    """POST /api/auth/refresh/ — Refresh access token."""
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh_token)
            return Response({
                'access': str(token.access_token),
                'refresh': str(token),
            })
        except TokenError as e:
            return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    """POST /api/auth/logout/ — Blacklist refresh token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            pass  # Already invalid
        return Response({'message': 'Logged out successfully.'})


class ProfileView(APIView):
    """GET/PATCH /api/auth/profile/ — Retrieve or update current user profile."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ — Change the current user's password."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response(
                {'error': 'current_password and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current_password):
            return Response({'error': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({'error': 'Password must be at least 8 characters'}, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save()
        return Response({'message': 'Password changed successfully.'})


class APITokenView(APIView):
    """
    GET  /api/auth/tokens/     — List all API tokens for current user
    POST /api/auth/tokens/     — Create a new API token
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tokens = APIToken.objects.filter(user=request.user, is_active=True)
        return Response(APITokenSerializer(tokens, many=True).data)

    def post(self, request):
        serializer = APITokenCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token_instance, raw_token = APIToken.generate(
            user=request.user,
            name=serializer.validated_data['name'],
        )

        data = APITokenSerializer(token_instance).data
        data['token'] = raw_token  # Show plain-text once only
        data['warning'] = 'Save this token — it will not be shown again.'

        return Response(data, status=status.HTTP_201_CREATED)


class APITokenDetailView(APIView):
    """DELETE /api/auth/tokens/<pk>/ — Revoke an API token."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            token = APIToken.objects.get(pk=pk, user=request.user)
        except APIToken.DoesNotExist:
            return Response({'error': 'Token not found'}, status=status.HTTP_404_NOT_FOUND)

        token.is_active = False
        token.save(update_fields=['is_active'])
        return Response({'message': 'Token revoked.'}, status=status.HTTP_200_OK)
