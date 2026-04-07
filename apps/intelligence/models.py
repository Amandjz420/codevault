from django.db import models


class IndexedFile(models.Model):
    """Tracks ingestion metadata for each Python file in a project."""
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='indexed_files',
    )
    file_path = models.CharField(max_length=500, help_text='Relative path within the project')
    file_hash = models.CharField(max_length=64, help_text='SHA-256 hash of file content')
    content = models.TextField(blank=True, help_text='Full source code of the file')
    last_indexed = models.DateTimeField()
    functions_count = models.IntegerField(default=0)
    classes_count = models.IntegerField(default=0)
    endpoints_count = models.IntegerField(default=0)
    signals_count = models.IntegerField(default=0)
    crons_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'intelligence_indexed_file'
        unique_together = ('project', 'file_path')
        verbose_name = 'Indexed File'
        verbose_name_plural = 'Indexed Files'
        ordering = ['file_path']

    def __str__(self):
        return f"{self.project.name}: {self.file_path}"

    @property
    def total_entities(self):
        return (
            self.functions_count + self.classes_count +
            self.endpoints_count + self.signals_count + self.crons_count
        )


class EntityDescription(models.Model):
    """
    Stores AI-generated descriptions for every code entity extracted during ingestion.
    Durable Postgres copy of what is also written to Neo4j node properties.

    One row per (project, file, entity_type, entity_name) — upserted on every ingestion.
    """

    ENTITY_TYPES = [
        ('function', 'Function'),
        ('class', 'Class'),
        ('endpoint', 'Endpoint'),
        ('model', 'Django Model'),
        ('file', 'File'),
    ]

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='entity_descriptions',
    )
    file_path = models.CharField(max_length=500)
    entity_type = models.CharField(max_length=20, choices=ENTITY_TYPES)
    entity_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'intelligence_entity_description'
        unique_together = ('project', 'file_path', 'entity_type', 'entity_name')
        verbose_name = 'Entity Description'
        verbose_name_plural = 'Entity Descriptions'
        indexes = [
            models.Index(fields=['project', 'entity_type']),
            models.Index(fields=['project', 'entity_name']),
        ]

    def __str__(self):
        return f"{self.entity_type}:{self.entity_name} ({self.file_path})"


class IngestionJob(models.Model):
    """Tracks the status of a codebase ingestion run."""

    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('webhook', 'GitHub Webhook'),
        ('scheduled', 'Scheduled'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='ingestion_jobs',
    )
    trigger = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    files_total = models.IntegerField(default=0)
    files_processed = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    triggered_by_commit = models.CharField(max_length=40, blank=True, help_text='Git commit SHA')
    celery_task_id = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'intelligence_ingestion_job'
        verbose_name = 'Ingestion Job'
        verbose_name_plural = 'Ingestion Jobs'
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.project.name} — {self.trigger} — {self.status}"

    @property
    def progress_percent(self):
        if self.files_total == 0:
            return 0
        return round((self.files_processed / self.files_total) * 100)

    @property
    def duration_seconds(self):
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class QueryLog(models.Model):
    """Logs every LLM query for analytics and debugging."""

    EFFORT_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]

    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='query_logs',
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='query_logs',
    )
    question = models.TextField()
    effort_level = models.CharField(max_length=10, choices=EFFORT_CHOICES, default='medium')
    llm_model = models.CharField(max_length=100, blank=True)
    answer = models.TextField()
    tokens_used = models.IntegerField(default=0)
    latency_ms = models.IntegerField(default=0)
    context_files = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'intelligence_query_log'
        verbose_name = 'Query Log'
        verbose_name_plural = 'Query Logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.project.name}: {self.question[:80]}"


class ProjectMemory(models.Model):
    """
    Rolling memory for a project — a continuously-updated summary of what has been
    learned through developer queries and code ingestion events.

    Updated asynchronously via Celery:
    - Every MEMORY_UPDATE_EVERY queries (from recent Q&A pairs)
    - After each ingestion (incorporating code change context)
    """
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.CASCADE,
        related_name='memory',
    )
    summary = models.TextField(
        blank=True,
        help_text='Rolling LLM-generated summary of codebase insights from queries and ingestions',
    )
    queries_since_update = models.IntegerField(
        default=0,
        help_text='Number of queries logged since the last memory update',
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'intelligence_project_memory'
        verbose_name = 'Project Memory'
        verbose_name_plural = 'Project Memories'

    def __str__(self):
        return f"{self.project.name} memory (updated {self.last_updated:%Y-%m-%d %H:%M})"
