import secrets
import requests as http_requests
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseRedirect
from urllib.parse import urlencode
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


# ------------------------------------------------------------------ #
#  GitHub OAuth                                                        #
# ------------------------------------------------------------------ #

_GITHUB_AUTH_URL = 'https://github.com/login/oauth/authorize'
_GITHUB_TOKEN_URL = 'https://github.com/login/oauth/access_token'
_GITHUB_USER_URL = 'https://api.github.com/user'
_STATE_TTL = 600  # 10 minutes


def _build_github_auth_url(state: str) -> str:
    return (
        f'{_GITHUB_AUTH_URL}'
        f'?client_id={settings.GITHUB_CLIENT_ID}'
        f'&redirect_uri={settings.GITHUB_REDIRECT_URI}'
        f'&scope=repo,read:user,user:email'
        f'&state={state}'
    )


class GitHubLoginInitView(APIView):
    """
    GET /api/auth/github/login/
    Public endpoint — no JWT needed.
    Starts the GitHub OAuth flow for sign-in / sign-up.
    Always 302-redirects directly to GitHub OAuth.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        if not settings.GITHUB_CLIENT_ID:
            return Response(
                {'error': 'GitHub OAuth is not configured on this server.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        state = secrets.token_urlsafe(24)
        # No user_id — callback will find/create user from GitHub profile
        cache.set(f'github_oauth_state:{state}', {'flow': 'login'}, _STATE_TTL)
        return HttpResponseRedirect(_build_github_auth_url(state))


class GitHubOAuthInitView(APIView):
    """
    GET /api/auth/github/
    Connect GitHub to an ALREADY authenticated account.

    Two usage modes:
    - API mode (frontend fetch):  send Authorization: Bearer <jwt> header
      → returns JSON { "authorization_url": "..." }
    - Browser redirect mode:      pass ?token=<jwt> as a query param
      → validates JWT, then 302-redirects directly to GitHub OAuth
      (used when the frontend cannot set headers on a window.location redirect)
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Resolve user — Bearer header OR ?token= query param
        user = None
        if request.user and request.user.is_authenticated:
            user = request.user
        else:
            raw_token = request.query_params.get('token', '')
            if raw_token:
                from rest_framework_simplejwt.tokens import UntypedToken
                from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
                from django.contrib.auth import get_user_model
                try:
                    validated = UntypedToken(raw_token)
                    user_id = validated.payload.get('user_id')
                    user = get_user_model().objects.get(pk=user_id)
                except (InvalidToken, TokenError, Exception):
                    return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_401_UNAUTHORIZED)

        if user is None:
            return Response({'error': 'Authentication required.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not settings.GITHUB_CLIENT_ID:
            return Response(
                {'error': 'GitHub OAuth is not configured on this server.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        state = secrets.token_urlsafe(24)
        # Store user_id so callback links GitHub to this account
        cache.set(f'github_oauth_state:{state}', {'flow': 'connect', 'user_id': user.pk}, _STATE_TTL)
        auth_url = _build_github_auth_url(state)

        # Browser redirect mode — called via window.location with ?token=
        if request.query_params.get('token'):
            return HttpResponseRedirect(auth_url)

        # API mode — called via fetch with Authorization header
        return Response({'authorization_url': auth_url})


class GitHubOAuthCallbackView(APIView):
    """
    GET /api/auth/github/callback/?code=<code>&state=<state>
    Exchange the temporary code for an access token, store it on the user,
    and return fresh JWT tokens.
    Called by GitHub after the user authorizes the OAuth App.
    """
    permission_classes = [AllowAny]

    def _redirect_error(self, message: str):
        """Redirect to frontend with an error param instead of showing a raw API error."""
        frontend_url = settings.GITHUB_FRONTEND_CALLBACK_URL
        params = urlencode({'error': message})
        return HttpResponseRedirect(f'{frontend_url}?{params}')

    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')

        if not code or not state:
            return self._redirect_error('Missing code or state.')

        state_data = cache.get(f'github_oauth_state:{state}')
        if not state_data:
            return self._redirect_error('Invalid or expired state. Please try again.')

        cache.delete(f'github_oauth_state:{state}')
        flow = state_data.get('flow')  # 'login' or 'connect'

        # Exchange code for GitHub access token
        token_resp = http_requests.post(
            _GITHUB_TOKEN_URL,
            json={
                'client_id': settings.GITHUB_CLIENT_ID,
                'client_secret': settings.GITHUB_CLIENT_SECRET,
                'code': code,
                'redirect_uri': settings.GITHUB_REDIRECT_URI,
            },
            headers={'Accept': 'application/json'},
            timeout=10,
        )
        if token_resp.status_code != 200:
            return self._redirect_error('Failed to exchange code with GitHub.')

        token_data = token_resp.json()
        access_token = token_data.get('access_token')
        if not access_token:
            return self._redirect_error(token_data.get('error_description', 'No access token returned.'))

        # Fetch GitHub user profile
        gh_headers = {'Authorization': f'token {access_token}', 'Accept': 'application/json'}
        user_resp = http_requests.get(_GITHUB_USER_URL, headers=gh_headers, timeout=10)
        if user_resp.status_code != 200:
            return self._redirect_error('Failed to fetch GitHub profile.')

        gh_profile = user_resp.json()
        github_id = str(gh_profile.get('id', ''))
        github_username = gh_profile.get('login', '')

        # ---- CONNECT flow: link GitHub to an already-authenticated account ----
        if flow == 'connect':
            user_id = state_data.get('user_id')
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                return self._redirect_error('User session expired. Please log in again.')

            user.github_id = github_id
            user.github_username = github_username
            user.github_access_token = access_token
            user.save(update_fields=['github_id', 'github_username', 'github_access_token'])

        # ---- LOGIN flow: sign in or register via GitHub ----
        else:
            # Try to find existing user by github_id first, then by email
            user = User.objects.filter(github_id=github_id).first()

            if user is None:
                # Resolve email — GitHub may not expose it in the profile
                email = gh_profile.get('email') or ''
                if not email:
                    emails_resp = http_requests.get(
                        'https://api.github.com/user/emails',
                        headers=gh_headers,
                        timeout=10,
                    )
                    if emails_resp.status_code == 200:
                        primary = next(
                            (e for e in emails_resp.json() if e.get('primary') and e.get('verified')),
                            None,
                        )
                        if primary:
                            email = primary['email']

                if not email:
                    return self._redirect_error(
                        'Your GitHub account has no verified public email. '
                        'Please add one on GitHub and try again.'
                    )

                # Find by email (existing CodeVault account) or create new user
                user = User.objects.filter(email=email).first()
                if user is None:
                    user = User.objects.create_user(
                        email=email,
                        name=gh_profile.get('name') or github_username,
                        password=None,  # unusable password — GitHub-only login
                    )

            # Always update GitHub fields
            user.github_id = github_id
            user.github_username = github_username
            user.github_access_token = access_token
            user.save(update_fields=['github_id', 'github_username', 'github_access_token'])

        tokens = get_tokens_for_user(user)
        frontend_url = settings.GITHUB_FRONTEND_CALLBACK_URL
        params = urlencode({
            'access': tokens['access'],
            'refresh': tokens['refresh'],
            'github_username': user.github_username,
        })
        return HttpResponseRedirect(f'{frontend_url}?{params}')


class GitHubDisconnectView(APIView):
    """POST /api/auth/github/disconnect/ — Unlink GitHub from this account."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        request.user.github_id = ''
        request.user.github_username = ''
        request.user.github_access_token = ''
        request.user.save(update_fields=['github_id', 'github_username', 'github_access_token'])
        return Response({'message': 'GitHub account disconnected.'})
