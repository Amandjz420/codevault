"""
Ingestion orchestrator — coordinates parser, graph, and vector services.
"""
import base64
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings
import requests as http_requests
from apps.intelligence.services.parsers import get_parser_for_file, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)

SKIP_DIRS = {
    'venv', '.venv', 'env', '.env', 'migrations',
    '__pycache__', '.git', 'node_modules', 'dist', 'build',
    '.tox', '.pytest_cache', '.mypy_cache', 'htmlcov',
}

# File size and project limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB default
MAX_FILES_PER_PROJECT = 10000


def get_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class IngestionOrchestrator:
    """Orchestrates the full ingestion pipeline for a project."""

    def __init__(self, project):
        from apps.intelligence.services.parser import CodeParser
        from apps.intelligence.services.graph import GraphService
        from apps.intelligence.services.vector import VectorService

        self.project = project
        self.parser = CodeParser()
        self.graph = GraphService(project.neo4j_namespace)
        self.vector = VectorService(project.chroma_collection)

    def close(self):
        self.graph.close()

    def should_skip(self, rel_path: Path) -> bool:
        return any(part in SKIP_DIRS for part in rel_path.parts)

    def ingest_local(self, root_path: str, job=None) -> dict:
        """
        Full ingestion of a local directory.
        Scans all supported code files, skips unchanged files (hash check),
        processes and stores changed ones.
        """
        from apps.intelligence.models import IndexedFile

        root = Path(root_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Path does not exist: {root_path}")

        stats = {"processed": 0, "skipped": 0, "errors": 0, "total": 0}

        # Scan for all supported file types
        code_files = []
        for ext in SUPPORTED_EXTENSIONS:
            pattern = f'*{ext}'
            for f in root.rglob(pattern):
                if not self.should_skip(f.relative_to(root)):
                    code_files.append(f)

        # Check file count limit
        max_files = getattr(settings, 'MAX_FILES_PER_PROJECT', MAX_FILES_PER_PROJECT)
        if len(code_files) > max_files:
            logger.warning(f"[Ingestion] Project has {len(code_files)} files, capping at {max_files}")
            code_files = code_files[:max_files]
            stats['total'] = max_files
        else:
            stats['total'] = len(code_files)

        if job:
            job.files_total = len(code_files)
            job.save(update_fields=['files_total'])

        for file_path in code_files:
            try:
                file_size = file_path.stat().st_size
                max_size = getattr(settings, 'MAX_FILE_SIZE_BYTES', MAX_FILE_SIZE)
                if file_size > max_size:
                    logger.warning(f"[Ingestion] Skipping {file_path}: exceeds max size ({file_size} > {max_size})")
                    stats['skipped'] += 1
                    continue

                with open(file_path, 'rb') as fh:
                    content = fh.read()

                rel_path = str(file_path.relative_to(root))
                file_hash = get_file_hash(content)

                existing = IndexedFile.objects.filter(
                    project=self.project, file_path=rel_path
                ).first()

                if existing and existing.file_hash == file_hash:
                    stats['skipped'] += 1
                else:
                    self._process_file(rel_path, content, file_hash, existing)
                    stats['processed'] += 1

                if job:
                    job.files_processed = stats['processed'] + stats['skipped']
                    job.save(update_fields=['files_processed'])

            except Exception as e:
                logger.error(f"[Ingestion] Error processing {file_path}: {e}")
                stats['errors'] += 1

        return stats

    def ingest_github_repo(
        self,
        repo: str,
        github_token: str,
        branch: str = 'main',
        job=None,
    ) -> dict:
        """
        Clone a GitHub repo to a temp directory and run a full local ingestion.
        Cleans up the temp directory afterwards regardless of success/failure.

        :param repo: 'owner/repo' string
        :param github_token: user's GitHub OAuth access token
        :param branch: branch to clone (default: 'main')
        :param job: optional IngestionJob ORM record for progress tracking
        """
        clone_url = f'https://x-access-token:{github_token}@github.com/{repo}.git'
        tmp_dir = tempfile.mkdtemp(prefix='codevault_gh_')
        logger.info(f"[Ingestion] Cloning {repo}@{branch} into {tmp_dir}")

        try:
            result = subprocess.run(
                ['git', 'clone', '--depth=1', '--branch', branch, clone_url, tmp_dir],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                # Sanitize token from error output before logging
                safe_err = result.stderr.replace(github_token, '***')
                raise RuntimeError(f"git clone failed: {safe_err}")

            logger.info(f"[Ingestion] Clone complete, starting ingestion for {repo}")
            return self.ingest_local(tmp_dir, job=job)

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def ingest_changed_files(
        self,
        changed_files: list,
        deleted_files: list,
        root_path: str = '',
        commit_sha: str = '',
        github_token: str = '',
    ) -> dict:
        """
        Incremental ingestion for GitHub webhook events.
        Processes only changed/added code files (all supported languages).

        File content is sourced from (in priority order):
          1. Local filesystem (root_path)
          2. GitHub Contents API (github_token + project.github_repo)
        """
        from apps.intelligence.models import IndexedFile

        stats = {"processed": 0, "deleted": 0, "errors": 0}

        # Resolve GitHub repo slug for API fetching
        github_repo = getattr(self.project, 'github_repo', '')

        # Handle deletions
        for file_path in deleted_files:
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            try:
                self.graph.delete_file(file_path)
                self.vector.delete_file(file_path)
                IndexedFile.objects.filter(
                    project=self.project, file_path=file_path
                ).delete()
                stats['deleted'] += 1
            except Exception as e:
                logger.error(f"[Ingestion] Error deleting {file_path}: {e}")
                stats['errors'] += 1

        # Handle changed/added files
        for file_path in changed_files:
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            if any(skip in file_path.split('/') for skip in SKIP_DIRS):
                continue

            content = None

            # 1. Try local filesystem
            if root_path:
                full_path = Path(root_path) / file_path
                if full_path.exists():
                    try:
                        with open(full_path, 'rb') as fh:
                            content = fh.read()
                    except Exception as e:
                        logger.warning(f"[Ingestion] Could not read local file {file_path}: {e}")

            # 2. Fall back to GitHub Contents API
            if content is None and github_token and github_repo:
                ref = commit_sha or 'HEAD'
                api_url = f'https://api.github.com/repos/{github_repo}/contents/{file_path}?ref={ref}'
                try:
                    resp = http_requests.get(
                        api_url,
                        headers={
                            'Authorization': f'token {github_token}',
                            'Accept': 'application/vnd.github.v3+json',
                        },
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = base64.b64decode(data['content'])
                    else:
                        logger.warning(
                            f"[Ingestion] GitHub API returned {resp.status_code} for {file_path}"
                        )
                except Exception as e:
                    logger.error(f"[Ingestion] GitHub API fetch failed for {file_path}: {e}")

            if content is None:
                logger.warning(f"[Ingestion] Skipping {file_path} — could not obtain content")
                stats['errors'] += 1
                continue

            try:
                file_hash = get_file_hash(content)
                existing = IndexedFile.objects.filter(
                    project=self.project, file_path=file_path
                ).first()
                self._process_file(file_path, content, file_hash, existing)
                stats['processed'] += 1
            except Exception as e:
                logger.error(f"[Ingestion] Error processing {file_path}: {e}")
                stats['errors'] += 1

        return stats

    def _process_file(self, rel_path: str, content: bytes, file_hash: str, existing_record=None):
        """Parse a single file and store it in graph + vector + ORM."""
        from apps.intelligence.models import IndexedFile
        from django.utils import timezone

        # Try language-specific parser first
        lang_parser = get_parser_for_file(rel_path)
        if lang_parser:
            parsed = lang_parser.parse(content, rel_path)
        else:
            # Fallback to Python parser for .py files
            parsed = self.parser.parse_file(content, rel_path)

        # Clear and re-ingest in graph + vector
        self.graph.delete_file(rel_path)
        self.graph.ingest_file(rel_path, parsed)

        self.vector.delete_file(rel_path)
        self.vector.ingest_file(rel_path, parsed)

        # Update ORM metadata
        IndexedFile.objects.update_or_create(
            project=self.project,
            file_path=rel_path,
            defaults={
                'file_hash': file_hash,
                'last_indexed': timezone.now(),
                'content': content.decode('utf-8', errors='replace'),
                'functions_count': len(parsed.functions),
                'classes_count': len(parsed.classes),
                'endpoints_count': len(parsed.endpoints),
                'signals_count': len(parsed.signals),
                'crons_count': len(parsed.cron_jobs),
            },
        )

        if parsed.errors:
            logger.warning(f"[Ingestion] {rel_path} had parse errors: {parsed.errors}")
