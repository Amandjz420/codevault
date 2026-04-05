from django.urls import path
from .views import MCPHttpView, MCPSSEView

urlpatterns = [
    # HTTP endpoint: single-request JSON-RPC
    # Compatible with: custom clients, testing
    path('http/', MCPHttpView.as_view(), name='mcp-http'),

    # SSE endpoint: streaming MCP
    # Compatible with: Cursor, Claude Desktop (remote), other SSE-based MCP clients
    path('sse/', MCPSSEView.as_view(), name='mcp-sse'),
]
