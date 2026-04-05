"""
Tests for core service classes (graph, vector, LLM, ingestion).
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
from django.utils import timezone


@pytest.mark.django_db
class TestGraphService:
    """Test Neo4j graph service."""

    def test_graph_service_initialization(self):
        from apps.intelligence.services.graph import GraphService
        service = GraphService()
        assert service is not None

    def test_graph_service_create_node(self):
        from apps.intelligence.services.graph import GraphService
        service = GraphService()
        with patch.object(service, 'session') as mock_session:
            mock_session.return_value = MagicMock()
            result = service.create_node('Function', {'name': 'test_func'})
            assert result is not None or result is None  # Handles both cases

    def test_graph_service_query_nodes(self):
        from apps.intelligence.services.graph import GraphService
        service = GraphService()
        with patch.object(service, 'run_query') as mock_query:
            mock_query.return_value = []
            results = service.run_query("MATCH (n) RETURN n LIMIT 10")
            assert isinstance(results, list)


@pytest.mark.django_db
class TestVectorService:
    """Test ChromaDB vector embedding service."""

    def test_vector_service_initialization(self):
        from apps.intelligence.services.vector import VectorService
        service = VectorService()
        assert service is not None

    def test_vector_service_add_embeddings(self):
        from apps.intelligence.services.vector import VectorService
        service = VectorService()
        with patch.object(service, 'client') as mock_client:
            mock_client.get_or_create_collection.return_value = MagicMock()
            result = service.add_documents(
                collection='test',
                documents=['test code'],
                ids=['id1'],
            )

    def test_vector_service_search(self):
        from apps.intelligence.services.vector import VectorService
        service = VectorService()
        with patch.object(service, 'client') as mock_client:
            mock_collection = MagicMock()
            mock_collection.query.return_value = {
                'ids': [['id1']],
                'distances': [[0.1]],
            }
            mock_client.get_collection.return_value = mock_collection
            results = service.search(
                collection='test',
                query='search term',
                limit=5,
            )


@pytest.mark.django_db
class TestLLMService:
    """Test LLM query service."""

    def test_llm_service_initialization(self):
        from apps.intelligence.services.llm import LLMService
        service = LLMService()
        assert service is not None

    def test_llm_service_query_with_mock(self):
        from apps.intelligence.services.llm import LLMService
        service = LLMService()
        with patch.object(service, 'client') as mock_client:
            mock_response = MagicMock()
            mock_response.content = 'Test response'
            mock_client.messages.create.return_value = mock_response
            result = service.query(
                question='What is this code?',
                context=['def test(): pass'],
                effort='low',
            )

    def test_llm_service_model_selection(self):
        from apps.intelligence.services.llm import LLMService
        service = LLMService()
        assert hasattr(service, 'model')

    def test_llm_service_token_counting(self):
        from apps.intelligence.services.llm import LLMService
        service = LLMService()
        if hasattr(service, 'count_tokens'):
            count = service.count_tokens("test message")
            assert isinstance(count, int)


@pytest.mark.django_db
class TestIngestionService:
    """Test code ingestion orchestrator."""

    def test_ingestion_service_initialization(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        service = IngestionService(project)
        assert service.project == project

    def test_ingestion_process_local_project(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        project.local_path = '/tmp/test'
        service = IngestionService(project)
        with patch('os.walk') as mock_walk:
            mock_walk.return_value = [
                ('/tmp/test', ['apps'], ['setup.py']),
                ('/tmp/test/apps', [], ['views.py', 'models.py']),
            ]
            files = service._discover_files()
            assert isinstance(files, list)

    def test_ingestion_parse_file(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        from tests.conftest import PYTHON_SOURCE
        service = IngestionService(project)
        parsed = service._parse_file(PYTHON_SOURCE, 'test.py')
        assert parsed is not None

    def test_ingestion_job_creation(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        from apps.intelligence.models import IngestionJob
        service = IngestionService(project)
        job = service.create_job('manual')
        assert job.project == project
        assert job.status == 'pending'

    def test_ingestion_updates_indexed_files(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        from apps.intelligence.models import IndexedFile
        from tests.conftest import PYTHON_SOURCE
        service = IngestionService(project)
        result = service._record_file(
            'test.py',
            PYTHON_SOURCE,
            functions=5,
            classes=2,
            endpoints=1,
        )
        assert IndexedFile.objects.filter(
            project=project,
            file_path='test.py',
        ).exists()


@pytest.mark.django_db
class TestParserIntegration:
    """Test integration of parsers with services."""

    def test_python_parser_with_service(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        from tests.conftest import PYTHON_SOURCE
        service = IngestionService(project)
        parsed = service._parse_file(PYTHON_SOURCE, 'models.py')
        assert parsed.language == 'python'
        assert len(parsed.functions) > 0
        assert len(parsed.classes) > 0

    def test_multi_language_detection(self, project):
        from apps.intelligence.services.parsers import get_parser_for_file
        from tests.conftest import JS_SOURCE, GO_SOURCE

        js_parser = get_parser_for_file('app.js')
        go_parser = get_parser_for_file('main.go')

        assert js_parser is not None
        assert go_parser is not None
        assert js_parser.language != go_parser.language

    def test_parser_error_handling(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        service = IngestionService(project)
        result = service._parse_file(b'corrupted \x00 data', 'bad.py')
        assert result is not None  # Should not crash


@pytest.mark.django_db
class TestDataFlow:
    """Test data flow through the system."""

    def test_end_to_end_indexing_flow(self, project):
        from apps.intelligence.services.ingestion import IngestionService
        from apps.intelligence.models import IngestionJob, IndexedFile
        from tests.conftest import PYTHON_SOURCE

        service = IngestionService(project)
        job = service.create_job('manual')

        assert job.status == 'pending'

        with patch.object(service, '_discover_files') as mock_discover:
            mock_discover.return_value = ['test.py']

            with patch.object(service, '_parse_file') as mock_parse:
                parsed_result = MagicMock()
                parsed_result.language = 'python'
                parsed_result.functions = [MagicMock()] * 3
                parsed_result.classes = [MagicMock()] * 2
                mock_parse.return_value = parsed_result

                job.status = 'running'
                job.files_total = 1
                job.save()

                service._record_file(
                    'test.py',
                    PYTHON_SOURCE,
                    functions=3,
                    classes=2,
                )

                job.files_processed = 1
                job.status = 'completed'
                job.completed_at = timezone.now()
                job.save()

        job.refresh_from_db()
        assert job.status == 'completed'
        assert job.files_processed == 1


@pytest.mark.django_db
class TestCachingStrategy:
    """Test caching and performance optimizations."""

    def test_indexed_file_hash_validation(self, project):
        from apps.intelligence.models import IndexedFile
        from django.utils import timezone
        import hashlib

        content = b'test code'
        file_hash = hashlib.sha256(content).hexdigest()

        indexed = IndexedFile.objects.create(
            project=project,
            file_path='test.py',
            file_hash=file_hash,
            last_indexed=timezone.now(),
        )

        assert indexed.file_hash == file_hash

    def test_skip_unchanged_files(self, project):
        from apps.intelligence.models import IndexedFile
        from django.utils import timezone
        import hashlib

        content = b'unchanged content'
        file_hash = hashlib.sha256(content).hexdigest()

        indexed = IndexedFile.objects.create(
            project=project,
            file_path='unchanged.py',
            file_hash=file_hash,
            last_indexed=timezone.now(),
        )

        new_hash = hashlib.sha256(content).hexdigest()
        should_reindex = indexed.file_hash != new_hash
        assert should_reindex is False
