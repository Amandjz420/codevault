#!/usr/bin/env python
"""
CodeVault MCP Server — stdio transport.

Usage (Claude Desktop / Cursor):
    python -m apps.mcp.server --api-url http://localhost:8000 --api-token <JWT>

The server implements the Model Context Protocol (MCP) 2024-11-05 spec over
stdin/stdout JSON-RPC, proxying tool calls to the CodeVault REST API.
"""
import sys
import json
import argparse
import logging
import os

# Configure Django settings before any app imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codevault.settings')

# Log to stderr (stdout is reserved for MCP JSON-RPC)
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format='%(levelname)s [%(name)s] %(message)s',
)
logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "codevault", "version": "2.0.0"}


class MCPServer:
    """stdio-transport MCP server. Proxies tool calls to CodeVault REST API."""

    def __init__(self, api_url: str, api_token: str):
        import requests as _requests
        self.api_url = api_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
        self._session = _requests.Session()
        self._session.headers.update(self.headers)

    # ------------------------------------------------------------------ #
    #  JSON-RPC dispatch                                                   #
    # ------------------------------------------------------------------ #

    def handle_request(self, request: dict) -> dict:
        method = request.get('method')
        params = request.get('params', {})
        req_id = request.get('id')

        try:
            if method == 'initialize':
                result = self._handle_initialize(params)
            elif method == 'initialized':
                # Notification — no response needed
                return None
            elif method == 'tools/list':
                result = self._handle_tools_list()
            elif method == 'tools/call':
                result = self._handle_tool_call(params)
            elif method == 'ping':
                result = {}
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        except Exception as e:
            logger.error(f"Error handling {method}: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _handle_initialize(self, params: dict) -> dict:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {},
            },
            "serverInfo": SERVER_INFO,
        }

    def _handle_tools_list(self) -> dict:
        from apps.mcp.tools import TOOLS
        return {"tools": TOOLS}

    def _handle_tool_call(self, params: dict) -> dict:
        tool_name = params.get('name')
        args = params.get('arguments', {})

        # Tools that don't need a project_slug
        if tool_name == 'list_projects':
            content = self._tool_list_projects(None, args)
            return {
                "content": [{"type": "text", "text": json.dumps(content, indent=2)}],
                "isError": False,
            }

        project_slug = args.get('project_slug', '')

        dispatch = {
            'search_codebase':     self._tool_search_codebase,
            'get_function':        self._tool_get_function,
            'get_class':           self._tool_get_class,
            'list_api_endpoints':  self._tool_list_endpoints,
            'list_models':         self._tool_list_models,
            'list_django_models':  self._tool_list_models,  # backward compat
            'ask_codebase':        self._tool_ask_codebase,
            'get_project_stats':   self._tool_get_stats,
            'list_files':          self._tool_list_files,
            'get_file_summary':    self._tool_get_file_summary,
            'get_dependency_graph': self._tool_get_dependency_graph,
        }

        handler = dispatch.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")

        content = handler(project_slug, args)
        return {
            "content": [{"type": "text", "text": json.dumps(content, indent=2)}],
            "isError": False,
        }

    # ------------------------------------------------------------------ #
    #  Individual tool implementations                                     #
    # ------------------------------------------------------------------ #

    def _get(self, path: str, params: dict = None):
        resp = self._session.get(f"{self.api_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict = None):
        resp = self._session.post(f"{self.api_url}{path}", json=data, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _tool_search_codebase(self, slug: str, args: dict):
        return self._get(
            f"/api/projects/{slug}/functions/",
            params={
                "search": args.get("query", ""),
                "limit": args.get("limit", 10),
            },
        )

    def _tool_get_function(self, slug: str, args: dict):
        return self._get(
            f"/api/projects/{slug}/functions/",
            params={"name": args.get("function_name", "")},
        )

    def _tool_list_endpoints(self, slug: str, args: dict):
        return self._get(f"/api/projects/{slug}/endpoints/")

    def _tool_list_models(self, slug: str, args: dict):
        return self._get(f"/api/projects/{slug}/models/")

    def _tool_ask_codebase(self, slug: str, args: dict):
        return self._post(
            f"/api/projects/{slug}/query/",
            data={
                "question": args.get("question", ""),
                "effort": args.get("effort", "medium"),
            },
        )

    def _tool_get_stats(self, slug: str, args: dict):
        return self._get(f"/api/projects/{slug}/stats/")

    def _tool_list_files(self, slug: str, args: dict):
        params = {}
        if args.get("search"):
            params["search"] = args["search"]
        return self._get(f"/api/projects/{slug}/files/", params=params)

    def _tool_get_class(self, slug: str, args: dict):
        return self._get(
            f"/api/projects/{slug}/models/",
            params={"name": args.get("class_name", "")},
        )

    def _tool_get_file_summary(self, slug: str, args: dict):
        return self._get(
            f"/api/projects/{slug}/files/",
            params={"path": args.get("file_path", "")},
        )

    def _tool_get_dependency_graph(self, slug: str, args: dict):
        return self._get(
            f"/api/projects/{slug}/functions/",
            params={
                "name": args.get("entity_name", ""),
                "depth": args.get("depth", 2),
            },
        )

    def _tool_list_projects(self, slug: str, args: dict):
        return self._get("/api/projects/")

    # ------------------------------------------------------------------ #
    #  stdio loop                                                          #
    # ------------------------------------------------------------------ #

    def run_stdio(self):
        logger.info("CodeVault MCP Server started (stdio)")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = self.handle_request(request)
                if response is not None:
                    print(json.dumps(response), flush=True)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from client: {e}")
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                print(json.dumps(error_resp), flush=True)


def main():
    parser = argparse.ArgumentParser(
        description='CodeVault MCP Server (stdio transport)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m apps.mcp.server --api-token eyJ...
  python -m apps.mcp.server --api-url https://codevault.example.com --api-token eyJ...
        """,
    )
    parser.add_argument(
        '--api-url',
        default='http://localhost:8000',
        help='CodeVault API base URL (default: http://localhost:8000)',
    )
    parser.add_argument(
        '--api-token',
        required=True,
        help='JWT access token (from POST /api/auth/login/)',
    )
    args = parser.parse_args()

    server = MCPServer(api_url=args.api_url, api_token=args.api_token)
    server.run_stdio()


if __name__ == '__main__':
    main()
