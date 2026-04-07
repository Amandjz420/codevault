from django.urls import path
from .views import MCPHttpView, MCPSSEView
from .oauth_views import OAuthRegisterView, OAuthAuthorizeView, OAuthTokenView

_register = OAuthRegisterView.as_view()
_authorize = OAuthAuthorizeView.as_view()
_token = OAuthTokenView.as_view()

urlpatterns = [
    # HTTP endpoint: single-request JSON-RPC
    path('http/', MCPHttpView.as_view(), name='mcp-http'),
    path('http', MCPHttpView.as_view()),

    # SSE endpoint: streaming MCP
    path('sse/', MCPSSEView.as_view(), name='mcp-sse'),
    path('sse', MCPSSEView.as_view()),

    # OAuth 2.0 — registered with AND without trailing slash so APPEND_SLASH
    # redirects (which turn POST→GET) never happen.
    path('oauth/register/', _register, name='mcp-oauth-register'),
    path('oauth/register', _register),
    path('oauth/authorize/', _authorize, name='mcp-oauth-authorize'),
    path('oauth/authorize', _authorize),
    path('oauth/token/', _token, name='mcp-oauth-token'),
    path('oauth/token', _token),
]
