"""
Celery tasks for asynchronous ingestion jobs.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


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
        return stats

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        logger.error(f"[Task] Ingestion failed for {project.name}: {exc}")
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

    try:
        orchestrator = IngestionOrchestrator(project)
        stats = orchestrator.ingest_changed_files(
            changed_files=changed_files,
            deleted_files=deleted_files,
            root_path=project.local_path or '',
            commit_sha=commit_sha,
        )
        orchestrator.close()

        job.status = 'completed'
        job.completed_at = timezone.now()
        job.files_processed = stats.get('processed', 0)
        job.save()

        project.last_indexed_at = timezone.now()
        project.save(update_fields=['last_indexed_at'])

        return stats

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        raise self.retry(exc=exc)
