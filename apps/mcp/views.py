"""
Django views for MCP over HTTP+SSE.
Supports remote MCP connections from clients like Cursor.
"""
import json
import logging
import time
from django.http import StreamingHttpResponse, JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "codevault", "version": "2.0.0"}


def _get_auth_user(request):
    """Authenticate via Bearer token (JWT or API token)."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None

    token = auth[7:]

    # Try API token first
    from apps.accounts.models import APIToken
    api_token = APIToken.verify(token)
    if api_token:
        return api_token.user

    # Try JWT
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        access = AccessToken(token)
        from apps.accounts.models import User
        return User.objects.get(id=access['user_id'])
    except Exception:
        return None


@method_decorator(csrf_exempt, name='dispatch')
class MCPHttpView(View):
    """
    POST /mcp/http/
    Single-request MCP endpoint for clients that don't support SSE.
    Body: JSON-RPC request
    Response: JSON-RPC response
    """

    def post(self, request):
        user = _get_auth_user(request)
        if not user:
            return JsonResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Unauthorized"}},
                status=401,
            )

        try:
            rpc_request = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                status=400,
            )

        result = self._dispatch(rpc_request, user)
        return JsonResponse(result)

    def _dispatch(self, request: dict, user) -> dict:
        method = request.get('method')
        params = request.get('params', {})
        req_id = request.get('id')

        try:
            if method == 'initialize':
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": SERVER_INFO,
                }
            elif method == 'tools/list':
                from apps.mcp.tools import TOOLS
                result = {"tools": TOOLS}

            elif method == 'tools/call':
                result = self._handle_tool_call(params, user)

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
            logger.error(f"[MCPHttp] Error in {method}: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _handle_tool_call(self, params: dict, user) -> dict:
        tool_name = params.get('name')
        args = params.get('arguments', {})

        # Tools that don't need a project
        if tool_name == 'list_projects':
            content = self._execute_tool_no_project(tool_name, args, user)
            return {
                "content": [{"type": "text", "text": json.dumps(content, indent=2)}],
                "isError": False,
            }

        project_slug = args.get('project_slug', '')
        from apps.projects.models import Project
        from django.shortcuts import get_object_or_404

        project = get_object_or_404(Project, slug=project_slug, is_active=True)
        if not project.user_has_access(user):
            raise PermissionError(f"Access denied to project '{project_slug}'")

        content = self._execute_tool(tool_name, project, args)
        return {
            "content": [{"type": "text", "text": json.dumps(content, indent=2)}],
            "isError": False,
        }

    def _execute_tool(self, tool_name: str, project, args: dict):
        from apps.intelligence.services.graph import GraphService
        from apps.intelligence.services.vector import VectorService
        from apps.intelligence.services.llm import LLMQueryService
        from apps.intelligence.models import IndexedFile

        if tool_name == 'search_codebase':
            from apps.intelligence.services.hybrid_search import HybridSearchService
            graph = GraphService(project.neo4j_namespace)
            vector = VectorService(project.chroma_collection)
            hybrid = HybridSearchService(graph, vector)
            filter_type = args.get('type_filter', 'any')
            result = hybrid.search(
                args.get('query', ''),
                n_results=args.get('limit', 10),
                filter_type=filter_type if filter_type != 'any' else None,
            )
            graph.close()
            return result

        elif tool_name == 'get_function':
            graph = GraphService(project.neo4j_namespace)
            result = graph.get_function_context(args.get('function_name', ''))
            graph.close()
            return result

        elif tool_name == 'list_api_endpoints':
            graph = GraphService(project.neo4j_namespace)
            result = graph.get_all_endpoints()
            graph.close()
            return result

        elif tool_name == 'list_django_models':
            graph = GraphService(project.neo4j_namespace)
            result = graph.get_all_models()
            graph.close()
            return result

        elif tool_name == 'ask_codebase':
            from apps.intelligence.models import QueryLog, ProjectMemory
            from apps.intelligence.tasks import update_project_memory, MEMORY_UPDATE_EVERY

            question = args.get('question', '')
            effort = args.get('effort', 'medium')

            memory, _ = ProjectMemory.objects.get_or_create(project=project)

            # Last 5 Q&A pairs sent as real conversation turns for continuity
            recent_logs = list(
                QueryLog.objects.filter(project=project)
                .order_by('-created_at')[:5]
            )
            recent_interactions = [
                {"question": log.question, "answer": log.answer}
                for log in reversed(recent_logs)  # oldest → newest
            ]

            graph = GraphService(project.neo4j_namespace)
            vector = VectorService(project.chroma_collection)
            llm = LLMQueryService(
                graph, vector,
                project_memory=memory.summary,
                recent_interactions=recent_interactions,
                project=project,
            )
            result = llm.query(question, effort)
            graph.close()

            # Log the query (no user attribution for MCP calls)
            QueryLog.objects.create(
                project=project,
                question=question,
                effort_level=effort,
                llm_model=result.get('model', ''),
                answer=result.get('answer', ''),
                tokens_used=result.get('tokens_used', 0),
                latency_ms=result.get('latency_ms', 0),
                context_files=result.get('context_files', []),
            )

            # Increment counter and trigger async memory refresh when threshold is reached
            ProjectMemory.objects.filter(project=project).update(
                queries_since_update=memory.queries_since_update + 1,
            )
            if memory.queries_since_update + 1 >= MEMORY_UPDATE_EVERY:
                update_project_memory.delay(project.id)

            return result

        elif tool_name == 'get_project_stats':
            graph = GraphService(project.neo4j_namespace)
            vector = VectorService(project.chroma_collection)
            stats = graph.get_project_stats()
            stats['vector_embeddings'] = vector.get_stats().get('total_embeddings', 0)
            graph.close()
            return stats

        elif tool_name == 'list_files':
            qs = IndexedFile.objects.filter(project=project)
            search = args.get('search', '')
            if search:
                qs = qs.filter(file_path__icontains=search)
            return [
                {
                    'file_path': f.file_path,
                    'functions': f.functions_count,
                    'classes': f.classes_count,
                    'endpoints': f.endpoints_count,
                    'last_indexed': f.last_indexed.isoformat() if f.last_indexed else None,
                }
                for f in qs.order_by('file_path')[:100]
            ]

        elif tool_name == 'get_class':
            graph = GraphService(project.neo4j_namespace)
            class_name = args.get('class_name', '')
            results = graph.query_graph("""
                MATCH (c:Class {name: $name, namespace: $ns})
                OPTIONAL MATCH (f:File)-[:DEFINES]->(c)
                RETURN c.name AS name,
                       c.code AS code,
                       c.bases AS bases,
                       c.is_django_model AS is_model,
                       c.docstring AS docstring,
                       c.start_line AS start_line,
                       c.end_line AS end_line,
                       f.path AS file_path
            """, {'name': class_name, 'ns': project.neo4j_namespace})
            graph.close()
            return results[0] if results else {"error": f"Class '{class_name}' not found"}

        elif tool_name == 'get_file_summary':
            graph = GraphService(project.neo4j_namespace)
            result = graph.get_file_summary(args.get('file_path', ''))
            graph.close()
            return result if result else {"error": "File not found in index"}

        elif tool_name == 'get_dependency_graph':
            graph = GraphService(project.neo4j_namespace)
            entity_name = args.get('entity_name', '')
            depth = min(args.get('depth', 2), 5)

            # Find the entity and its connections
            results = graph.query_graph("""
                MATCH (n {namespace: $ns})
                WHERE n.name = $name AND (n:Function OR n:Class)
                OPTIONAL MATCH (ep:APIEndpoint)-[:TRIGGERS]->(n)
                OPTIONAL MATCH (s:Signal)-[:HANDLED_BY]->(n)
                OPTIONAL MATCH (f:File)-[:DEFINES]->(n)
                OPTIONAL MATCH (n)-[:DEFINES]->(child)
                RETURN n.name AS name,
                       labels(n) AS types,
                       n.file_path AS file_path,
                       collect(DISTINCT ep.pattern) AS triggered_by_endpoints,
                       collect(DISTINCT s.signal_type) AS handles_signals,
                       collect(DISTINCT {name: child.name, type: labels(child)}) AS defines,
                       f.path AS defined_in
            """, {'name': entity_name, 'ns': project.neo4j_namespace})
            graph.close()
            return results[0] if results else {"error": f"Entity '{entity_name}' not found"}

        elif tool_name == 'list_models':
            # Alias for list_django_models - works for all model types now
            graph = GraphService(project.neo4j_namespace)
            result = graph.get_all_models()
            graph.close()
            return result

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    def _execute_tool_no_project(self, tool_name: str, args: dict, user):
        if tool_name == 'list_projects':
            from apps.projects.models import Project as ProjectModel
            from django.db.models import Q
            projects = ProjectModel.objects.filter(
                Q(owner=user) | Q(project_members__user=user),
                is_active=True,
            ).distinct().values(
                'name', 'slug', 'description', 'language', 'last_indexed_at',
            )[:50]
            return [
                {
                    'name': p['name'],
                    'slug': p['slug'],
                    'description': p['description'],
                    'language': p['language'],
                    'last_indexed': p['last_indexed_at'].isoformat() if p['last_indexed_at'] else None,
                }
                for p in projects
            ]
        raise ValueError(f"Unknown tool: {tool_name}")


@method_decorator(csrf_exempt, name='dispatch')
class MCPSSEView(View):
    """
    GET  /mcp/sse/ — SSE stream for MCP initialization
    POST /mcp/sse/ — Post JSON-RPC messages (Cursor-style)

    Implements a basic SSE-based MCP transport compatible with Cursor.
    """

    def get(self, request):
        """Open SSE connection and send server capabilities."""
        user = _get_auth_user(request)
        if not user:
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        def event_stream():
            # Send initial server info as SSE event
            init_msg = json.dumps({
                "jsonrpc": "2.0",
                "method": "server/ready",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {}},
                },
            })
            yield f"data: {init_msg}\n\n"

            # Keep connection alive
            while True:
                time.sleep(15)
                yield "data: {\"jsonrpc\":\"2.0\",\"method\":\"ping\"}\n\n"

        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    def post(self, request):
        """Accept JSON-RPC POST requests over the SSE channel."""
        user = _get_auth_user(request)
        if not user:
            return JsonResponse(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Unauthorized"}},
                status=401,
            )

        # Reuse the HTTP view's dispatch logic
        http_view = MCPHttpView()
        http_view.request = request
        return http_view.post(request)
