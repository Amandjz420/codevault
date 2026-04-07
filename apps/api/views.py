"""
DRF REST API views for CodeVault.
All views require JWT authentication and project membership checks.
"""
import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle
from django.shortcuts import get_object_or_404
from django.utils import timezone

logger = logging.getLogger(__name__)


class QueryRateThrottle(UserRateThrottle):
    scope = 'query'


from apps.projects.models import Project
from apps.projects.serializers import ProjectSerializer, ProjectCreateSerializer, ProjectUpdateSerializer
from apps.intelligence.models import IndexedFile, IngestionJob, QueryLog, ProjectMemory
from .serializers import (
    IndexedFileSerializer,
    IngestionJobSerializer,
    QuerySerializer,
    QueryLogSerializer,
    TriggerIngestionSerializer,
    GraphStatsSerializer,
)


def get_project_or_403(slug, user):
    """Return (project, None) or (None, error_response)."""
    project = get_object_or_404(Project, slug=slug, is_active=True)
    if not project.user_has_access(user):
        return None, Response(
            {'error': 'Project not found or access denied.'},
            status=status.HTTP_404_NOT_FOUND,
        )
    return project, None


def get_project_write_or_403(slug, user):
    """Return (project, None) or (None, error_response) with write check."""
    project, err = get_project_or_403(slug, user)
    if err:
        return None, err
    if not project.user_can_write(user):
        return None, Response(
            {'error': 'Write access required.'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return project, None


# ------------------------------------------------------------------ #
#  Project CRUD                                                        #
# ------------------------------------------------------------------ #

class ProjectListCreateView(APIView):
    """
    GET  /api/projects/   — List all accessible projects
    POST /api/projects/   — Create a new project
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(project_members__user=request.user),
            is_active=True,
        ).distinct().select_related('owner').prefetch_related('project_members')
        serializer = ProjectSerializer(projects, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        project = serializer.save()
        return Response(
            ProjectSerializer(project, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    """
    GET    /api/projects/<slug>/
    PATCH  /api/projects/<slug>/
    DELETE /api/projects/<slug>/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err
        return Response(ProjectSerializer(project, context={'request': request}).data)

    def patch(self, request, slug):
        project, err = get_project_write_or_403(slug, request.user)
        if err:
            return err
        serializer = ProjectUpdateSerializer(project, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(ProjectSerializer(project, context={'request': request}).data)

    def delete(self, request, slug):
        project = get_object_or_404(Project, slug=slug, is_active=True)
        if project.owner != request.user:
            return Response(
                {'error': 'Only the owner can delete a project.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        project.is_active = False
        project.save(update_fields=['is_active'])
        return Response({'message': 'Project deleted.'}, status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ #
#  Members                                                             #
# ------------------------------------------------------------------ #

class ProjectMemberListCreateView(APIView):
    """
    GET  /api/projects/<slug>/members/
    POST /api/projects/<slug>/members/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err
        from apps.projects.serializers import ProjectMemberSerializer
        members = project.project_members.select_related('user')
        return Response(ProjectMemberSerializer(members, many=True).data)

    def post(self, request, slug):
        project, err = get_project_write_or_403(slug, request.user)
        if err:
            return err
        from apps.projects.serializers import ProjectMemberCreateSerializer, ProjectMemberSerializer
        from apps.projects.models import ProjectMember
        serializer = ProjectMemberCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.user
        if project.owner == user:
            return Response({'error': 'User is already the project owner.'}, status=status.HTTP_400_BAD_REQUEST)
        member, created = ProjectMember.objects.get_or_create(
            project=project, user=user,
            defaults={'role': serializer.validated_data['role'], 'invited_by': request.user},
        )
        if not created:
            member.role = serializer.validated_data['role']
            member.save(update_fields=['role'])
        return Response(
            ProjectMemberSerializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProjectMemberDetailView(APIView):
    """
    PATCH  /api/projects/<slug>/members/<pk>/
    DELETE /api/projects/<slug>/members/<pk>/
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, slug, pk):
        project, err = get_project_write_or_403(slug, request.user)
        if err:
            return err
        from apps.projects.models import ProjectMember
        from apps.projects.serializers import ProjectMemberSerializer
        member = get_object_or_404(ProjectMember, pk=pk, project=project)
        role = request.data.get('role')
        if role not in ('admin', 'member', 'viewer'):
            return Response({'error': 'Invalid role. Use: admin, member, viewer.'}, status=status.HTTP_400_BAD_REQUEST)
        member.role = role
        member.save(update_fields=['role'])
        return Response(ProjectMemberSerializer(member).data)

    def delete(self, request, slug, pk):
        project, err = get_project_write_or_403(slug, request.user)
        if err:
            return err
        from apps.projects.models import ProjectMember
        member = get_object_or_404(ProjectMember, pk=pk, project=project)
        if member.user == project.owner:
            return Response({'error': 'Cannot remove the project owner.'}, status=status.HTTP_400_BAD_REQUEST)
        member.delete()
        return Response({'message': 'Member removed.'}, status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ #
#  Graph / Intelligence                                                #
# ------------------------------------------------------------------ #

class GraphStatsView(APIView):
    """GET /api/projects/<slug>/stats/ — Graph statistics + vector count."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        try:
            from apps.intelligence.services.graph import GraphService
            from apps.intelligence.services.vector import VectorService
            graph = GraphService(project.neo4j_namespace)
            vector = VectorService(project.chroma_collection)
            stats = graph.get_project_stats()
            stats['vector_embeddings'] = vector.get_stats().get('total_embeddings', 0)
            graph.close()
            return Response(stats)
        except Exception as e:
            logger.error(f"[GraphStatsView] {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GraphFilesView(APIView):
    """GET /api/projects/<slug>/files/ — List indexed files with metadata."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        qs = IndexedFile.objects.filter(project=project)
        search = request.query_params.get('search')
        if search:
            qs = qs.filter(file_path__icontains=search)
        qs = qs.order_by('file_path')

        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 200)
        start = (page - 1) * page_size
        total = qs.count()
        files = qs[start:start + page_size]

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': IndexedFileSerializer(files, many=True).data,
        })


class GraphFunctionsView(APIView):
    """GET /api/projects/<slug>/functions/?search=<query>&name=<exact>"""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        search = request.query_params.get('search', '')
        name = request.query_params.get('name', '')

        try:
            from apps.intelligence.services.graph import GraphService
            graph = GraphService(project.neo4j_namespace)
            if name:
                results = [graph.get_function_context(name)]
                results = [r for r in results if r]
            else:
                results = graph.search_functions(search or '')
            graph.close()
            return Response(results)
        except Exception as e:
            logger.error(f"[GraphFunctionsView] {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GraphEndpointsView(APIView):
    """GET /api/projects/<slug>/endpoints/ — List all API endpoints."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        try:
            from apps.intelligence.services.graph import GraphService
            graph = GraphService(project.neo4j_namespace)
            endpoints = graph.get_all_endpoints()
            graph.close()
            return Response(endpoints)
        except Exception as e:
            logger.error(f"[GraphEndpointsView] {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GraphModelsView(APIView):
    """GET /api/projects/<slug>/models/ — List all Django ORM models."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        try:
            from apps.intelligence.services.graph import GraphService
            graph = GraphService(project.neo4j_namespace)
            models = graph.get_all_models()
            graph.close()
            return Response(models)
        except Exception as e:
            logger.error(f"[GraphModelsView] {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class QueryView(APIView):
    """
    POST /api/projects/<slug>/query/
    Body: {"question": "...", "effort": "medium"}
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [QueryRateThrottle]

    def post(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        serializer = QuerySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = serializer.validated_data['question']
        effort = serializer.validated_data['effort']

        try:
            from apps.intelligence.services.graph import GraphService
            from apps.intelligence.services.vector import VectorService
            from apps.intelligence.services.llm import LLMQueryService
            from apps.intelligence.tasks import update_project_memory, MEMORY_UPDATE_EVERY

            # Load (or initialise) the rolling project memory for context injection
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

            # Log the query
            QueryLog.objects.create(
                project=project,
                user=request.user,
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

            return Response(result)

        except Exception as e:
            logger.error(f"[QueryView] {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class IngestionJobListView(APIView):
    """GET /api/projects/<slug>/jobs/ — List ingestion jobs for a project."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err

        jobs = IngestionJob.objects.filter(project=project).order_by('-started_at')[:50]
        return Response(IngestionJobSerializer(jobs, many=True).data)


class TriggerIngestionView(APIView):
    """
    POST /api/projects/<slug>/ingest/
    Body: {"path": "/absolute/path", "sync": false, "clear": false}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        project, err = get_project_write_or_403(slug, request.user)
        if err:
            return err

        serializer = TriggerIngestionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        path = serializer.validated_data['path']
        sync = serializer.validated_data['sync']
        clear = serializer.validated_data['clear']

        import os
        if not os.path.isdir(path):
            return Response(
                {'error': f"Path does not exist: {path}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optionally clear existing data
        if clear:
            try:
                from apps.intelligence.services.graph import GraphService
                from apps.intelligence.services.vector import VectorService
                graph = GraphService(project.neo4j_namespace)
                vector = VectorService(project.chroma_collection)
                graph.clear_project()
                vector.delete_collection()
                graph.close()
                project.indexed_files.all().delete()
            except Exception as e:
                logger.warning(f"[TriggerIngestion] Clear error: {e}")

        if sync:
            from apps.intelligence.models import IngestionJob
            from apps.intelligence.services.ingestion import IngestionOrchestrator

            job = IngestionJob.objects.create(
                project=project, trigger='manual', status='running',
            )
            try:
                orc = IngestionOrchestrator(project)
                stats = orc.ingest_local(path, job=job)
                orc.close()
                job.status = 'completed'
                job.completed_at = timezone.now()
                job.save()
                project.last_indexed_at = timezone.now()
                project.save(update_fields=['last_indexed_at'])
                return Response({
                    'message': 'Ingestion complete.',
                    'job_id': job.id,
                    'stats': stats,
                })
            except Exception as e:
                job.status = 'failed'
                job.error_message = str(e)
                job.completed_at = timezone.now()
                job.save()
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            from apps.intelligence.tasks import run_local_ingestion
            task = run_local_ingestion.delay(project.id, path)
            return Response({
                'message': 'Ingestion queued.',
                'task_id': str(task.id),
            }, status=status.HTTP_202_ACCEPTED)


class QueryLogListView(APIView):
    """GET /api/projects/<slug>/query-logs/ — List recent query logs."""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project, err = get_project_or_403(slug, request.user)
        if err:
            return err
        logs = QueryLog.objects.filter(project=project).order_by('-created_at')[:100]
        return Response(QueryLogSerializer(logs, many=True).data)


# ------------------------------------------------------------------ #
#  GitHub Integration                                                  #
# ------------------------------------------------------------------ #

class ListGithubRepoBranchesView(APIView):
    """
    GET /api/github/repos/<owner>/<repo>/branches/
    Proxies https://api.github.com/repos/{owner}/{repo}/branches using the
    authenticated user's stored GitHub token. Returns the array as-is
    (each item: name, commit.sha, protected).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, owner, repo):
        import requests as http_requests

        token = request.user.github_access_token
        if not token:
            return Response(
                {'error': 'GitHub account not connected. Visit /api/auth/github/ first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resp = http_requests.get(
                f'https://api.github.com/repos/{owner}/{repo}/branches',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json',
                },
                params={'per_page': 100},
                timeout=15,
            )
        except Exception as e:
            logger.error(f"[ListGithubRepoBranchesView] {e}")
            return Response({'error': 'Failed to reach GitHub API.'}, status=status.HTTP_502_BAD_GATEWAY)

        if resp.status_code == 404:
            return Response({'error': f'Repository {owner}/{repo} not found or not accessible.'}, status=status.HTTP_404_NOT_FOUND)
        if resp.status_code == 401:
            return Response({'error': 'GitHub token is invalid or expired.'}, status=status.HTTP_401_UNAUTHORIZED)
        if resp.status_code != 200:
            return Response({'error': 'GitHub API error.'}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(resp.json())


class ListGithubReposView(APIView):
    """
    GET /api/github/repos/
    Returns the authenticated user's GitHub repos (up to 100, sorted by
    last push). Requires the user to have connected their GitHub account.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import requests as http_requests

        token = request.user.github_access_token
        if not token:
            return Response(
                {'error': 'GitHub account not connected. Visit /api/auth/github/ first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        page = int(request.query_params.get('page', 1))
        try:
            resp = http_requests.get(
                'https://api.github.com/user/repos',
                headers={
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json',
                },
                params={
                    'sort': 'pushed',
                    'per_page': 50,
                    'page': page,
                    'affiliation': 'owner,collaborator,organization_member',
                },
                timeout=15,
            )
        except Exception as e:
            logger.error(f"[ListGithubReposView] {e}")
            return Response({'error': 'Failed to reach GitHub API.'}, status=status.HTTP_502_BAD_GATEWAY)

        if resp.status_code == 401:
            return Response(
                {'error': 'GitHub token is invalid or expired. Reconnect via /api/auth/github/.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if resp.status_code != 200:
            return Response({'error': 'GitHub API error.'}, status=status.HTTP_502_BAD_GATEWAY)

        repos = [
            {
                'full_name': r['full_name'],
                'name': r['name'],
                'description': r.get('description', ''),
                'private': r['private'],
                'default_branch': r['default_branch'],
                'html_url': r['html_url'],
                'pushed_at': r.get('pushed_at'),
                'language': r.get('language'),
            }
            for r in resp.json()
        ]
        return Response({'repos': repos, 'page': page})


class TriggerGithubIngestionView(APIView):
    """
    POST /api/projects/<slug>/ingest/github/
    Queues a full GitHub repo ingestion for the project.
    The project must have github_repo set (owner/repo).
    The calling user must have their GitHub account connected.
    Body (optional): {"branch": "main", "clear": false}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, slug):
        project, err = get_project_write_or_403(slug, request.user)
        if err:
            return err

        if not request.user.github_access_token:
            return Response(
                {'error': 'GitHub account not connected. Visit /api/auth/github/ first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        github_repo = request.data.get('github_repo') or project.github_repo
        if not github_repo:
            return Response(
                {'error': 'No GitHub repo configured. Provide github_repo (owner/repo) in the request body or set it on the project.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch = request.data.get('branch') or project.github_default_branch or 'main'
        commit_sha = request.data.get('commit_sha', '')
        clear = request.data.get('clear', False)

        # Persist repo/branch on the project if provided
        update_fields = []
        if github_repo != project.github_repo:
            project.github_repo = github_repo
            update_fields.append('github_repo')
        if branch != project.github_default_branch:
            project.github_default_branch = branch
            update_fields.append('github_default_branch')
        if update_fields:
            project.save(update_fields=update_fields)

        if clear:
            try:
                from apps.intelligence.services.graph import GraphService
                from apps.intelligence.services.vector import VectorService
                graph = GraphService(project.neo4j_namespace)
                vector = VectorService(project.chroma_collection)
                graph.clear_project()
                vector.delete_collection()
                graph.close()
                project.indexed_files.all().delete()
            except Exception as e:
                logger.warning(f"[TriggerGithubIngestion] Clear error: {e}")

        from apps.intelligence.tasks import run_github_ingestion
        task = run_github_ingestion.delay(project.id, request.user.id, commit_sha)

        logger.info(
            f"[TriggerGithubIngestion] Queued for {project.name} "
            f"repo={github_repo} branch={branch} sha={commit_sha or 'HEAD'} task={task.id}"
        )

        return Response({
            'message': 'GitHub ingestion queued.',
            'task_id': str(task.id),
            'github_repo': github_repo,
            'branch': branch,
            'commit_sha': commit_sha or None,
        }, status=status.HTTP_202_ACCEPTED)
