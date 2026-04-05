"""
GitHub webhook handler for CodeVault.
Validates HMAC-SHA256 signatures and queues incremental ingestion tasks.
"""
import hashlib
import hmac
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


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


@csrf_exempt
@require_POST
def github_webhook(request, project_slug: str):
    """
    POST /api/webhooks/github/<project_slug>/
    Receives GitHub push events and queues incremental ingestion.
    """
    from apps.projects.models import Project
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

    commit_sha = payload.get('after', '')
    commits = payload.get('commits', [])

    changed_files: set = set()
    deleted_files: set = set()

    for commit in commits:
        changed_files.update(commit.get('added', []))
        changed_files.update(commit.get('modified', []))
        deleted_files.update(commit.get('removed', []))

    # Filter to Python files only
    changed_py = [f for f in changed_files if f.endswith('.py')]
    deleted_py = [f for f in deleted_files if f.endswith('.py')]

    if not changed_py and not deleted_py:
        return JsonResponse({'message': 'No Python files changed — nothing to do.'})

    task = run_webhook_ingestion.delay(
        project.id,
        changed_py,
        deleted_py,
        commit_sha,
    )

    logger.info(
        f"[Webhook] Queued ingestion for {project.name}, "
        f"commit {commit_sha[:8]}, task {task.id}"
    )

    return JsonResponse({
        'message': 'Ingestion queued.',
        'task_id': str(task.id),
        'commit': commit_sha[:8],
        'changed_files': len(changed_py),
        'deleted_files': len(deleted_py),
    })
