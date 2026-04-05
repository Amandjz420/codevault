"""
Management command: ingest a local Python project into CodeVault.

Usage:
    python manage.py ingest_local <project_slug> <path>
    python manage.py ingest_local <project_slug> <path> --sync
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Ingest a local Python project into CodeVault'

    def add_arguments(self, parser):
        parser.add_argument('project_slug', type=str, help='Slug of the project to ingest into')
        parser.add_argument('path', type=str, help='Absolute path to the Python project root')
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Run synchronously (default: queue via Celery)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear all existing graph/vector data before ingesting',
        )

    def handle(self, *args, **options):
        from apps.projects.models import Project
        from apps.intelligence.models import IngestionJob
        from apps.intelligence.tasks import run_local_ingestion
        from django.utils import timezone
        import os

        slug = options['project_slug']
        path = options['path']

        if not os.path.isdir(path):
            raise CommandError(f"Path does not exist or is not a directory: {path}")

        try:
            project = Project.objects.get(slug=slug)
        except Project.DoesNotExist:
            raise CommandError(f"Project with slug '{slug}' not found.")

        self.stdout.write(f"Project:  {project.name} (slug={project.slug})")
        self.stdout.write(f"Path:     {path}")
        self.stdout.write(f"Neo4j NS: {project.neo4j_namespace}")
        self.stdout.write(f"Chroma:   {project.chroma_collection}")

        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            from apps.intelligence.services.ingestion import IngestionOrchestrator
            orc = IngestionOrchestrator(project)
            orc.graph.clear_project()
            orc.vector.delete_collection()
            orc.close()
            project.indexed_files.all().delete()
            self.stdout.write(self.style.WARNING('Cleared.'))

        if options['sync']:
            self.stdout.write('Running synchronously...')
            job = IngestionJob.objects.create(
                project=project,
                trigger='manual',
                status='running',
            )
            from apps.intelligence.services.ingestion import IngestionOrchestrator
            orchestrator = IngestionOrchestrator(project)
            stats = orchestrator.ingest_local(path, job=job)
            orchestrator.close()
            job.status = 'completed'
            job.completed_at = timezone.now()
            job.save()
            project.last_indexed_at = timezone.now()
            project.save(update_fields=['last_indexed_at'])
            self.stdout.write(self.style.SUCCESS(
                f"Done! processed={stats['processed']} "
                f"skipped={stats['skipped']} errors={stats['errors']}"
            ))
        else:
            self.stdout.write('Queuing Celery task...')
            task = run_local_ingestion.delay(project.id, path)
            self.stdout.write(self.style.SUCCESS(f"Queued! Task ID: {task.id}"))
            self.stdout.write(f"Monitor: celery -A codevault inspect active")
