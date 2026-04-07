from django.urls import path
from .views import MCPHttpView, MCPSSEView
from .oauth_views import OAuthRegisterView, OAuthAuthorizeView, OAuthTokenView

urlpatterns = [
    # HTTP endpoint: single-request JSON-RPC
    # Compatible with: custom clients, testing
    path('http/', MCPHttpView.as_view(), name='mcp-http'),

    # SSE endpoint: streaming MCP
    # Compatible with: Cursor, Claude Desktop (remote), other SSE-based MCP clients
    path('sse/', MCPSSEView.as_view(), name='mcp-sse'),

    # OAuth 2.0 Authorization Server endpoints
    path('oauth/register/', OAuthRegisterView.as_view(), name='mcp-oauth-register'),
    path('oauth/authorize/', OAuthAuthorizeView.as_view(), name='mcp-oauth-authorize'),
    path('oauth/token/', OAuthTokenView.as_view(), name='mcp-oauth-token'),
]
