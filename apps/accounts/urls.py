from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    RefreshView,
    LogoutView,
    ProfileView,
    ChangePasswordView,
    APITokenView,
    APITokenDetailView,
    GitHubOAuthInitView,
    GitHubOAuthCallbackView,
    GitHubDisconnectView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', RefreshView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('profile/', ProfileView.as_view(), name='auth-profile'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('tokens/', APITokenView.as_view(), name='auth-tokens'),
    path('tokens/<int:pk>/', APITokenDetailView.as_view(), name='auth-token-detail'),
    # GitHub OAuth
    path('github/', GitHubOAuthInitView.as_view(), name='auth-github-init'),
    path('github/callback/', GitHubOAuthCallbackView.as_view(), name='auth-github-callback'),
    path('github/disconnect/', GitHubDisconnectView.as_view(), name='auth-github-disconnect'),
]
