"""
Celery tasks for asynchronous ingestion jobs and project memory updates.

Ingestion is parallelised: a coordinator task scans/fetches the file list and
dispatches N `process_*_file_chunk` tasks (one per CHUNK_SIZE files) that run
concurrently across all available Celery workers.  A chord callback
(`finalize_ingestion_job`) aggregates results and marks the job complete.
"""
import logging
import os
from pathlib import Path

from celery import chord, group, shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# How many files each parallel chunk task processes.
# Tune via settings.INGESTION_CHUNK_SIZE (default 15).
CHUNK_SIZE = getattr(settings, 'INGESTION_CHUNK_SIZE', 15)

# Trigger a memory refresh after this many queries have been logged
MEMORY_UPDATE_EVERY = 5


# --------------------------------------------------------------------------- #
#  Local ingestion                                                              #
# --------------------------------------------------------------------------- #

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_local_ingestion(self, project_id: int, path: str):
    """
    Coordinator: scan the local directory, filter unchanged files, then dispatch
    parallel `process_local_file_chunk` tasks for everything that needs work.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import IngestionJob, IndexedFile
    from apps.intelligence.services.ingestion import (
        SKIP_DIRS, get_file_hash, MAX_FILE_SIZE, MAX_FILES_PER_PROJECT,
    )
    from apps.intelligence.services.parsers import SUPPORTED_EXTENSIONS

    project = Project.objects.get(id=project_id)
    job = IngestionJob.objects.create(
        project=project,
        trigger='manual',
        status='running',
        celery_task_id=self.request.id or '',
    )

    try:
        root = Path(path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        max_files = getattr(settings, 'MAX_FILES_PER_PROJECT', MAX_FILES_PER_PROJECT)
        max_size = getattr(settings, 'MAX_FILE_SIZE_BYTES', MAX_FILE_SIZE)

        # Collect all candidate files
        all_files = []
        for ext in SUPPORTED_EXTENSIONS:
            for f in root.rglob(f'*{ext}'):
                if not any(part in SKIP_DIRS for part in f.relative_to(root).parts):
                    all_files.append(f)
        all_files = all_files[:max_files]

        # Filter to only changed/new files (hash check)
        changed_paths = []
        for f in all_files:
            if f.stat().st_size > max_size:
                continue
            try:
                content = f.read_bytes()
                rel_path = str(f.relative_to(root))
                file_hash = get_file_hash(content)
                existing = IndexedFile.objects.filter(project=project, file_path=rel_path).first()
                if not existing or existing.file_hash != file_hash:
                    changed_paths.append(str(f))
            except Exception as e:
                logger.warning(f"[Ingestion] Could not read {f}: {e}")

        total = len(all_files)
        pre_skipped = total - len(changed_paths)

        job.files_total = total
        job.files_processed = pre_skipped
        job.save(update_fields=['files_total', 'files_processed'])

        if not changed_paths:
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            refresh_memory_on_ingestion.delay(project_id, [], {'processed': 0, 'skipped': pre_skipped, 'total': total})
            return {'processed': 0, 'skipped': pre_skipped, 'errors': 0, 'total': total}

        chunks = [changed_paths[i:i + CHUNK_SIZE] for i in range(0, len(changed_paths), CHUNK_SIZE)]
        logger.info(f"[Task] Dispatching {len(chunks)} parallel chunks ({len(changed_paths)} files) for '{project.name}'")

        chord(
            group(process_local_file_chunk.s(project_id, job.id, chunk, path) for chunk in chunks)
        )(finalize_ingestion_job.s(project_id, job.id, pre_skipped, total))

        return {'dispatched_chunks': len(chunks), 'files_to_process': len(changed_paths)}

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        logger.error(f"[Task] Local ingestion coordinator failed for project {project_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def process_local_file_chunk(self, project_id: int, job_id: int, file_paths: list, root_path: str):
    """
    Process a chunk of local files.  Runs concurrently with sibling chunks on
    other Celery workers.  Returns {'processed': N, 'skipped': 0, 'errors': K}.
    """
    from apps.projects.models import Project
    from apps.intelligence.models import IndexedFile
    from apps.intelligence.services.ingestion import IngestionOrchestrator, get_file_hash

    project = Project.objects.get(id=project_id)
    root = Path(root_path).resolve()
    orchestrator = IngestionOrchestrator(project)
    stats = {'processed': 0, 'skipped': 0, 'errors': 0}

    for abs_path_str in file_paths:
        f = Path(abs_path_str)
        rel_path = str(f.relative_to(root))
        try:
            content = f.read_bytes()
            file_hash = get_file_hash(content)
            existing = IndexedFile.objects.filter(project=project, file_path=rel_path).first()
            orchestrator._process_file(rel_path, content, file_hash, existing)
            stats['processed'] += 1
        except Exception as e:
            logger.error(f"[Task] Error processing {rel_path}: {e}")
            stats['errors'] += 1

    orchestrator.close()
    return stats


# --------------------------------------------------------------------------- #
#  GitHub full ingestion                                                        #
# --------------------------------------------------------------------------- #

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_github_ingestion(self, project_id: int, triggered_by_user_id: int, commit_sha: str = ''):
    """
    Coordinator: fetch the GitHub file tree, then dispatch parallel
    `process_github_file_chunk` tasks.
    """
    import requests as http_requests
    from apps.projects.models import Project
    from apps.accounts.models import User
    from apps.intelligence.models import IngestionJob
    from apps.intelligence.services.ingestion import (
        SKIP_DIRS, MAX_FILE_SIZE, MAX_FILES_PER_PROJECT, IngestionOrchestrator,
    )
    from apps.intelligence.services.parsers import SUPPORTED_EXTENSIONS

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
        gh_headers = {
            'Authorization': f'token {user.github_access_token}',
            'Accept': 'application/vnd.github.v3+json',
        }

        # Resolve commit SHA
        tmp = IngestionOrchestrator(project)
        sha = commit_sha or tmp._resolve_commit_sha(
            project.github_repo, user.github_access_token,
            project.github_default_branch or 'main',
        )
        tmp.close()

        logger.info(f"[Task] Fetching tree for {project.github_repo}@{sha[:8]}")

        tree_url = f'https://api.github.com/repos/{project.github_repo}/git/trees/{sha}?recursive=1'
        tree_resp = http_requests.get(tree_url, headers=gh_headers, timeout=30)
        tree_resp.raise_for_status()
        tree_data = tree_resp.json()

        if tree_data.get('truncated'):
            logger.warning(f"[Task] Tree is truncated for {project.github_repo} — repo may be very large")

        max_files = getattr(settings, 'MAX_FILES_PER_PROJECT', MAX_FILES_PER_PROJECT)
        max_size = getattr(settings, 'MAX_FILE_SIZE_BYTES', MAX_FILE_SIZE)

        code_files = []
        for item in tree_data.get('tree', []):
            if item['type'] != 'blob':
                continue
            fpath = item['path']
            if os.path.splitext(fpath)[1].lower() not in SUPPORTED_EXTENSIONS:
                continue
            if any(part in SKIP_DIRS for part in Path(fpath).parts):
                continue
            if item.get('size', 0) > max_size:
                continue
            code_files.append(fpath)

        code_files = code_files[:max_files]
        total = len(code_files)

        job.files_total = total
        job.save(update_fields=['files_total'])

        if not code_files:
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            return {'processed': 0, 'skipped': 0, 'errors': 0, 'total': 0}

        chunks = [code_files[i:i + CHUNK_SIZE] for i in range(0, len(code_files), CHUNK_SIZE)]
        logger.info(f"[Task] Dispatching {len(chunks)} parallel GitHub chunks ({total} files) for '{project.name}'")

        chord(
            group(
                process_github_file_chunk.s(
                    project_id, job.id, chunk,
                    project.github_repo, sha, user.github_access_token,
                )
                for chunk in chunks
            )
        )(finalize_ingestion_job.s(project_id, job.id, 0, total))

        return {'dispatched_chunks': len(chunks), 'files_to_process': total}

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save()
        logger.error(f"[Task] GitHub ingestion coordinator failed for project {project_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def process_github_file_chunk(
    self,
    project_id: int,
    job_id: int,
    file_paths: list,
    repo: str,
    sha: str,
    github_token: str,
):
    """
    Download and process a chunk of GitHub files concurrently with sibling chunks.
    Returns {'processed': N, 'skipped': M, 'errors': K}.
    """
    import requests as http_requests
    from apps.projects.models import Project
    from apps.intelligence.models import IndexedFile
    from apps.intelligence.services.ingestion import IngestionOrchestrator, get_file_hash

    project = Project.objects.get(id=project_id)
    orchestrator = IngestionOrchestrator(project)
    raw_base = f'https://raw.githubusercontent.com/{repo}/{sha}'
    stats = {'processed': 0, 'skipped': 0, 'errors': 0}

    for file_path in file_paths:
        try:
            resp = http_requests.get(
                f'{raw_base}/{file_path}',
                headers={'Authorization': f'token {github_token}'},
                timeout=15,
            )
            if resp.status_code == 404:
                logger.warning(f"[Task] 404 for {file_path} — skipping")
                stats['skipped'] += 1
                continue
            resp.raise_for_status()
            content = resp.content

            file_hash = get_file_hash(content)
            existing = IndexedFile.objects.filter(project=project, file_path=file_path).first()
            if existing and existing.file_hash == file_hash:
                stats['skipped'] += 1
            else:
                orchestrator._process_file(file_path, content, file_hash, existing)
                stats['processed'] += 1
        except Exception as e:
            logger.error(f"[Task] Error processing GitHub file {file_path}: {e}")
            stats['errors'] += 1

    orchestrator.close()
    return stats


# --------------------------------------------------------------------------- #
#  Chord callback — shared by both local and GitHub ingestion                  #
# --------------------------------------------------------------------------- #

@shared_task
def finalize_ingestion_job(chunk_results: list, project_id: int, job_id: int, pre_skipped: int, total: int):
    """
    Chord callback: aggregate all chunk stats and mark the IngestionJob complete.
    `pre_skipped` is the count of files the coordinator already determined were
    unchanged (local ingestion only; 0 for GitHub).
    """
    from apps.projects.models import Project
    from apps.intelligence.models import IngestionJob

    safe = [r for r in chunk_results if isinstance(r, dict)]
    processed = sum(r.get('processed', 0) for r in safe)
    skipped = pre_skipped + sum(r.get('skipped', 0) for r in safe)
    errors = sum(r.get('errors', 0) for r in safe)

    job = IngestionJob.objects.get(id=job_id)
    job.status = 'completed'
    job.completed_at = timezone.now()
    job.files_processed = processed + skipped
    job.files_total = total
    job.save()

    project = Project.objects.get(id=project_id)
    project.last_indexed_at = timezone.now()
    project.save(update_fields=['last_indexed_at'])

    stats = {'processed': processed, 'skipped': skipped, 'errors': errors, 'total': total}
    logger.info(f"[Task] Ingestion finalized for project {project_id}: {stats}")
    refresh_memory_on_ingestion.delay(project_id, [], stats)
    return stats


# --------------------------------------------------------------------------- #
#  Webhook ingestion (incremental — typically small, stays single-task)        #
# --------------------------------------------------------------------------- #

@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def run_webhook_ingestion(
    self,
    project_id: int,
    changed_files: list,
    deleted_files: list,
    commit_sha: str,
):
    """
    Incremental ingestion triggered by GitHub webhook.
    Webhook pushes are typically small (few files), so this stays a single task.
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

        refresh_memory_on_ingestion.delay(project_id, changed_files, stats)
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
    """
    from apps.intelligence.services.memory import update_memory_from_ingestion
    try:
        update_memory_from_ingestion(project_id, changed_files, stats)
    except Exception as exc:
        logger.error(f"[Task] Ingestion memory refresh failed for project {project_id}: {exc}")
        raise self.retry(exc=exc)
