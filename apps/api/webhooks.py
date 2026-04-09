"""
GitHub webhook handler for CodeVault.
Validates HMAC-SHA256 signatures, filters by watched branch, and queues
incremental ingestion tasks for all supported languages.
"""
import hashlib
import hmac
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

# All file extensions recognised by the CodeVault parser
SUPPORTED_EXTENSIONS = (
    '.py',                          # Python
    '.js', '.jsx', '.ts', '.tsx',   # JavaScript / TypeScript
    '.go',                          # Go
    '.rs',                          # Rust
    '.java',                        # Java
)


def verify_github_signature(request, secret: str) -> bool:
    """Validate GitHub HMAC-SHA256 webhook signature."""
    sig_header = request.headers.get('X-Hub-Signature-256', '')
    if not sig_header.startswith('sha256='):
        return False

    expected = hmac.new(
        secret.encode('utf-8'),
        request.body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", sig_header)


def _is_supported(filename: str) -> bool:
    return any(filename.endswith(ext) for ext in SUPPORTED_EXTENSIONS)


@csrf_exempt
@require_POST
def github_webhook(request, project_slug: str):
    """
    POST /api/webhooks/github/<project_slug>/
    Receives GitHub push events, validates the branch against the project's
    configured webhook_branch (or github_default_branch), and queues
    incremental ingestion for all supported languages.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import WebhookEvent
    from apps.intelligence.tasks import run_webhook_ingestion

    try:
        project = Project.objects.get(slug=project_slug, is_active=True)
    except Project.DoesNotExist:
        return JsonResponse({'error': 'Project not found'}, status=404)

    if not project.github_webhook_secret:
        return JsonResponse(
            {'error': 'Webhook secret not configured for this project.'},
            status=400,
        )

    if not verify_github_signature(request, project.github_webhook_secret):
        logger.warning(f"[Webhook] Invalid HMAC signature for project {project_slug}")
        return JsonResponse({'error': 'Invalid signature'}, status=401)

    event = request.headers.get('X-GitHub-Event', '')

    if event == 'ping':
        return JsonResponse({'message': 'pong', 'project': project.name})

    if event != 'push':
        return JsonResponse({'message': f"Event '{event}' ignored — only 'push' is handled."})

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    # ------------------------------------------------------------------ #
    #  Branch filtering                                                    #
    # ------------------------------------------------------------------ #
    ref = payload.get('ref', '')                          # e.g. refs/heads/main
    pushed_branch = ref.removeprefix('refs/heads/')       # e.g. main

    watched_branch = project.webhook_branch or project.github_default_branch or 'main'

    if pushed_branch != watched_branch:
        logger.info(
            f"[Webhook] {project.name}: push to '{pushed_branch}' ignored "
            f"(watching '{watched_branch}')"
        )
        return JsonResponse({
            'message': f"Branch '{pushed_branch}' is not watched (watching '{watched_branch}').",
            'watched_branch': watched_branch,
        })

    # ------------------------------------------------------------------ #
    #  Collect changed files across all commits                           #
    # ------------------------------------------------------------------ #
    commit_sha = payload.get('after', '')
    commits = payload.get('commits', [])

    # Use the HEAD commit message and pusher for logging
    head_commit = payload.get('head_commit') or {}
    commit_message = head_commit.get('message', '')
    pusher = payload.get('pusher', {}).get('name', '')

    changed_files: set = set()
    deleted_files: set = set()

    for commit in commits:
        changed_files.update(commit.get('added', []))
        changed_files.update(commit.get('modified', []))
        deleted_files.update(commit.get('removed', []))

    # Filter to supported languages only
    changed_supported = [f for f in changed_files if _is_supported(f)]
    deleted_supported = [f for f in deleted_files if _is_supported(f)]

    if not changed_supported and not deleted_supported:
        return JsonResponse({
            'message': 'No supported source files changed — nothing to do.',
            'branch': pushed_branch,
            'commit': commit_sha[:8],
        })

    # ------------------------------------------------------------------ #
    #  Queue ingestion task                                                #
    # ------------------------------------------------------------------ #
    try:
        task = run_webhook_ingestion.delay(
            project.id,
            changed_supported,
            deleted_supported,
            commit_sha,
        )
        task_id = str(task.id)
        event_status = 'queued'
    except Exception as broker_exc:
        # Redis/broker unreachable — log clearly and return 503 so GitHub
        # will retry the delivery later
        logger.error(
            f"[Webhook] Failed to queue ingestion task for {project.name} "
            f"branch={pushed_branch} commit={commit_sha[:8]}: {broker_exc}"
        )
        return JsonResponse(
            {
                'error': 'Celery broker unreachable — task could not be queued.',
                'detail': str(broker_exc),
                'branch': pushed_branch,
                'commit': commit_sha[:8],
            },
            status=503,
        )

    # ------------------------------------------------------------------ #
    #  Persist webhook event log                                           #
    # ------------------------------------------------------------------ #
    try:
        WebhookEvent.objects.create(
            project=project,
            branch=pushed_branch,
            commit_sha=commit_sha,
            commit_message=commit_message[:500],
            pusher=pusher,
            changed_files=changed_supported,
            deleted_files=deleted_supported,
            status=event_status,
            celery_task_id=task_id,
        )
    except Exception as db_exc:
        # Log but don't fail — task is already queued, event log is secondary
        logger.error(f"[Webhook] Could not save WebhookEvent for {project.name}: {db_exc}")

    logger.info(
        f"[Webhook] Queued ingestion for {project.name} "
        f"branch={pushed_branch} commit={commit_sha[:8]} task={task_id} "
        f"changed={len(changed_supported)} deleted={len(deleted_supported)}"
    )

    return JsonResponse({
        'message': 'Ingestion queued.',
        'task_id': task_id,
        'branch': pushed_branch,
        'commit': commit_sha[:8],
        'changed_files': len(changed_supported),
        'deleted_files': len(deleted_supported),
    })
