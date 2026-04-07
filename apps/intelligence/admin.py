from django.contrib import admin
from .models import IndexedFile, IngestionJob, QueryLog, ProjectMemory


@admin.register(IndexedFile)
class IndexedFileAdmin(admin.ModelAdmin):
    list_display = (
        'file_path', 'project', 'functions_count', 'classes_count',
        'endpoints_count', 'signals_count', 'crons_count', 'last_indexed',
    )
    list_filter = ('project',)
    search_fields = ('file_path', 'project__name')
    readonly_fields = ('file_hash', 'last_indexed')
    ordering = ['project', 'file_path']

    def total_entities(self, obj):
        return obj.total_entities
    total_entities.short_description = 'Total Entities'


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = (
        'project', 'trigger', 'status',
        'files_processed', 'files_total', 'progress_percent',
        'started_at', 'completed_at',
    )
    list_filter = ('trigger', 'status', 'project')
    search_fields = ('project__name', 'triggered_by_commit', 'celery_task_id')
    readonly_fields = (
        'started_at', 'completed_at', 'files_processed', 'files_total',
        'celery_task_id', 'progress_percent', 'duration_seconds',
    )
    ordering = ['-started_at']

    def progress_percent(self, obj):
        return f"{obj.progress_percent}%"
    progress_percent.short_description = 'Progress'


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    list_display = (
        'project', 'user', 'effort_level', 'llm_model',
        'tokens_used', 'latency_ms', 'created_at',
    )
    list_filter = ('project', 'effort_level', 'llm_model')
    search_fields = ('question', 'project__name', 'user__email')
    readonly_fields = ('created_at', 'tokens_used', 'latency_ms', 'context_files')
    ordering = ['-created_at']

    def question_preview(self, obj):
        return obj.question[:100]
    question_preview.short_description = 'Question'


@admin.register(ProjectMemory)
class ProjectMemoryAdmin(admin.ModelAdmin):
    list_display = ('project', 'queries_since_update', 'summary_preview', 'last_updated')
    list_filter = ('project',)
    search_fields = ('project__name', 'summary')
    readonly_fields = ('last_updated', 'queries_since_update')
    ordering = ['-last_updated']
    fields = ('project', 'summary', 'queries_since_update', 'last_updated')

    def summary_preview(self, obj):
        return obj.summary[:120] + '…' if len(obj.summary) > 120 else obj.summary or '(empty)'
    summary_preview.short_description = 'Summary preview'
