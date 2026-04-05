from rest_framework import serializers
from apps.intelligence.models import IndexedFile, IngestionJob, QueryLog


class IndexedFileSerializer(serializers.ModelSerializer):
    total_entities = serializers.ReadOnlyField()

    class Meta:
        model = IndexedFile
        fields = (
            'id', 'file_path', 'file_hash',
            'last_indexed', 'functions_count', 'classes_count',
            'endpoints_count', 'signals_count', 'crons_count',
            'total_entities',
        )
        read_only_fields = fields


class IngestionJobSerializer(serializers.ModelSerializer):
    progress_percent = serializers.ReadOnlyField()
    duration_seconds = serializers.ReadOnlyField()

    class Meta:
        model = IngestionJob
        fields = (
            'id', 'trigger', 'status',
            'files_total', 'files_processed', 'progress_percent',
            'error_message', 'started_at', 'completed_at',
            'triggered_by_commit', 'celery_task_id', 'duration_seconds',
        )
        read_only_fields = fields


class QuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)
    effort = serializers.ChoiceField(
        choices=['low', 'medium', 'high'],
        default='medium',
    )


class QueryResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    effort = serializers.CharField()
    model = serializers.CharField()
    tokens_used = serializers.IntegerField()
    latency_ms = serializers.IntegerField()
    context_files = serializers.ListField(child=serializers.CharField())


class QueryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryLog
        fields = (
            'id', 'question', 'effort_level', 'llm_model',
            'answer', 'tokens_used', 'latency_ms',
            'context_files', 'created_at',
        )
        read_only_fields = fields


class TriggerIngestionSerializer(serializers.Serializer):
    path = serializers.CharField(
        max_length=500,
        help_text='Absolute path to the local project directory',
    )
    sync = serializers.BooleanField(
        default=False,
        help_text='Run synchronously instead of queuing as a Celery task',
    )
    clear = serializers.BooleanField(
        default=False,
        help_text='Clear all existing graph/vector data before ingesting',
    )


class GraphStatsSerializer(serializers.Serializer):
    files = serializers.IntegerField()
    functions = serializers.IntegerField()
    classes = serializers.IntegerField()
    endpoints = serializers.IntegerField()
    signals = serializers.IntegerField()
    cron_jobs = serializers.IntegerField()
    vector_embeddings = serializers.IntegerField()
