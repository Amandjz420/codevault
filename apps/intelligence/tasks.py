"""
Celery tasks for asynchronous ingestion jobs and project memory updates.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# Trigger a memory refresh after this many queries have been logged
MEMORY_UPDATE_EVERY = 5


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_local_ingestion(self, project_id: int, path: str):
    """
    Celery task: ingest a local directory for the given project.
    Creates an IngestionJob record and runs the full pipeline.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import IngestionJob
    from apps.intelligence.services.ingestion import IngestionOrchestrator

    project = Project.objects.get(id=project_id)
    job = IngestionJob.objects.create(
        project=project,
        trigger='manual',
        status='running',
        celery_task_id=self.request.id or '',
    )

    try:
        orchestrator = IngestionOrchestrator(project)
        stats = orchestrator.ingest_local(path, job=job)
        orchestrator.close()

        job.status = 'completed'
        job.completed_at = timezone.now()
        job.files_processed = stats.get('processed', 0) + stats.get('skipped', 0)
        job.files_total = stats.get('total', job.files_total)
        job.save()

        project.last_indexed_at = timezone.now()
        project.save(update_fields=['last_indexed_at'])

        logger.info(f"[Task] Ingestion complete for {project.name}: {stats}")

        # Update project memory to reflect the newly ingested code
        refresh_memory_on_ingestion.delay(project.id, [], stats)

        return stats

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        logger.error(f"[Task] Ingestion failed for {project.name}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_github_ingestion(self, project_id: int, triggered_by_user_id: int, commit_sha: str = ''):
    """
    Celery task: full ingestion of a GitHub repo.
    Clones the repo using the triggering user's GitHub access token,
    runs the full pipeline, then cleans up.
    """
    from apps.projects.models import Project
    from apps.accounts.models import User
    from apps.intelligence.models import IngestionJob
    from apps.intelligence.services.ingestion import IngestionOrchestrator

    project = Project.objects.get(id=project_id)
    user = User.objects.get(id=triggered_by_user_id)

    if not project.github_repo:
        raise ValueError(f"Project {project.slug} has no github_repo configured.")
    if not user.github_access_token:
        raise ValueError(f"User {user.email} has no GitHub access token. Connect GitHub first.")

    job = IngestionJob.objects.create(
        project=project,
        trigger='github',
        status='running',
        celery_task_id=self.request.id or '',
    )

    try:
        orchestrator = IngestionOrchestrator(project)
        stats = orchestrator.ingest_github_repo(
            repo=project.github_repo,
            github_token=user.github_access_token,
            branch=project.github_default_branch or 'main',
            commit_sha=commit_sha,
            job=job,
        )
        orchestrator.close()

        job.status = 'completed'
        job.completed_at = timezone.now()
        job.files_processed = stats.get('processed', 0) + stats.get('skipped', 0)
        job.files_total = stats.get('total', job.files_total)
        job.save()

        project.last_indexed_at = timezone.now()
        project.save(update_fields=['last_indexed_at'])

        logger.info(f"[Task] GitHub ingestion complete for {project.name}: {stats}")
        refresh_memory_on_ingestion.delay(project.id, [], stats)
        return stats

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        logger.error(f"[Task] GitHub ingestion failed for {project.name}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def run_webhook_ingestion(
    self,
    project_id: int,
    changed_files: list,
    deleted_files: list,
    commit_sha: str,
):
    """
    Celery task: incremental ingestion triggered by GitHub webhook.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import IngestionJob
    from apps.intelligence.services.ingestion import IngestionOrchestrator

    project = Project.objects.get(id=project_id)
    job = IngestionJob.objects.create(
        project=project,
        trigger='webhook',
        status='running',
        triggered_by_commit=commit_sha,
        files_total=len(changed_files),
        celery_task_id=self.request.id or '',
    )

    # Use the project owner's GitHub token for fetching file content via API
    github_token = project.owner.github_access_token if hasattr(project, 'owner') else ''

    try:
        orchestrator = IngestionOrchestrator(project)
        stats = orchestrator.ingest_changed_files(
            changed_files=changed_files,
            deleted_files=deleted_files,
            root_path=project.local_path or '',
            commit_sha=commit_sha,
            github_token=github_token,
        )
        orchestrator.close()

        job.status = 'completed'
        job.completed_at = timezone.now()
        job.files_processed = stats.get('processed', 0)
        job.save()

        project.last_indexed_at = timezone.now()
        project.save(update_fields=['last_indexed_at'])

        # Update project memory with the specific files that changed
        refresh_memory_on_ingestion.delay(project.id, changed_files, stats)

        return stats

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        raise self.retry(exc=exc)


# --------------------------------------------------------------------------- #
#  Memory tasks                                                                #
# --------------------------------------------------------------------------- #

@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def update_project_memory(self, project_id: int):
    """
    Regenerate the project memory summary from recent Q&A pairs.
    Triggered automatically every MEMORY_UPDATE_EVERY queries.
    """
    from apps.intelligence.services.memory import update_memory_from_queries
    try:
        update_memory_from_queries(project_id)
    except Exception as exc:
        logger.error(f"[Task] Memory update failed for project {project_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def refresh_memory_on_ingestion(self, project_id: int, changed_files: list, stats: dict):
    """
    Update the project memory summary after a code ingestion completes.
    Incorporates which files changed so future queries know about recent code evolution.
    """
    from apps.intelligence.services.memory import update_memory_from_ingestion
    try:
        update_memory_from_ingestion(project_id, changed_files, stats)
    except Exception as exc:
        logger.error(f"[Task] Ingestion memory refresh failed for project {project_id}: {exc}")
        raise self.retry(exc=exc)
