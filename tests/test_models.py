"""
Tests for Django models.
"""
import pytest
from django.test import TestCase
from django.utils import timezone


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        from apps.accounts.models import User
        user = User.objects.create_user(email='test@test.com', password='pass123')
        assert user.email == 'test@test.com'
        assert user.username is None
        assert user.check_password('pass123')

    def test_display_name_with_name(self):
        from apps.accounts.models import User
        user = User(email='test@test.com', name='John Doe')
        assert user.display_name == 'John Doe'

    def test_display_name_without_name(self):
        from apps.accounts.models import User
        user = User(email='john@test.com', name='')
        assert user.display_name == 'john'

    def test_user_string_representation(self):
        from apps.accounts.models import User
        user = User(email='test@example.com')
        assert str(user) == 'test@example.com'


@pytest.mark.django_db
class TestAPITokenModel:
    def test_generate_token(self):
        from apps.accounts.models import User, APIToken
        user = User.objects.create_user(email='test@test.com', password='pass123')
        token_obj, raw_token = APIToken.generate(user, 'Test Token')
        assert token_obj.name == 'Test Token'
        assert token_obj.prefix == raw_token[:8]
        assert len(raw_token) > 20

    def test_verify_token(self):
        from apps.accounts.models import User, APIToken
        user = User.objects.create_user(email='test@test.com', password='pass123')
        _, raw_token = APIToken.generate(user, 'Test Token')
        verified = APIToken.verify(raw_token)
        assert verified is not None
        assert verified.user == user

    def test_verify_invalid_token(self):
        from apps.accounts.models import APIToken
        verified = APIToken.verify('invalid-token-string')
        assert verified is None

    def test_verify_expired_token(self):
        from apps.accounts.models import User, APIToken
        user = User.objects.create_user(email='test@test.com', password='pass123')
        token_obj, raw_token = APIToken.generate(user, 'Expired Token')
        token_obj.expires_at = timezone.now() - timezone.timedelta(days=1)
        token_obj.save()
        verified = APIToken.verify(raw_token)
        assert verified is None

    def test_verify_inactive_token(self):
        from apps.accounts.models import User, APIToken
        user = User.objects.create_user(email='test@test.com', password='pass123')
        token_obj, raw_token = APIToken.generate(user, 'Inactive Token')
        token_obj.is_active = False
        token_obj.save()
        verified = APIToken.verify(raw_token)
        assert verified is None

    def test_token_updates_last_used(self):
        from apps.accounts.models import User, APIToken
        user = User.objects.create_user(email='test@test.com', password='pass123')
        token_obj, raw_token = APIToken.generate(user, 'Test Token')
        assert token_obj.last_used is None
        APIToken.verify(raw_token)
        token_obj.refresh_from_db()
        assert token_obj.last_used is not None


@pytest.mark.django_db
class TestProjectModel:
    def test_auto_slug_generation(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        user = User.objects.create_user(email='test@test.com', password='pass123')
        project = Project.objects.create(name='My Cool Project', owner=user)
        assert project.slug == 'my-cool-project'

    def test_auto_namespace_generation(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        user = User.objects.create_user(email='test@test.com', password='pass123')
        project = Project.objects.create(name='Test Project', owner=user)
        assert project.neo4j_namespace == project.slug
        assert project.chroma_collection.startswith('cv_')

    def test_user_has_access_owner(self, user, project):
        assert project.user_has_access(user) is True

    def test_user_has_access_member(self, project_with_member):
        project, member_user, _ = project_with_member
        assert project.user_has_access(member_user) is True

    def test_user_has_no_access(self, project):
        from apps.accounts.models import User
        stranger = User.objects.create_user(email='stranger@test.com', password='pass123')
        assert project.user_has_access(stranger) is False

    def test_user_can_write_owner(self, user, project):
        assert project.user_can_write(user) is True

    def test_viewer_cannot_write(self, project):
        from apps.accounts.models import User
        from apps.projects.models import ProjectMember
        viewer = User.objects.create_user(email='viewer@test.com', password='pass123')
        ProjectMember.objects.create(project=project, user=viewer, role='viewer')
        assert project.user_can_write(viewer) is False

    def test_member_can_write(self, project):
        from apps.accounts.models import User
        from apps.projects.models import ProjectMember
        member = User.objects.create_user(email='member@test.com', password='pass123')
        ProjectMember.objects.create(project=project, user=member, role='member')
        assert project.user_can_write(member) is True

    def test_admin_can_write(self, project):
        from apps.accounts.models import User
        from apps.projects.models import ProjectMember
        admin = User.objects.create_user(email='admin@test.com', password='pass123')
        ProjectMember.objects.create(project=project, user=admin, role='admin')
        assert project.user_can_write(admin) is True

    def test_get_member_role_owner(self, user, project):
        assert project.get_member_role(user) == 'owner'

    def test_get_member_role_member(self, project_with_member):
        project, member_user, _ = project_with_member
        assert project.get_member_role(member_user) == 'member'

    def test_get_member_role_none(self, project):
        from apps.accounts.models import User
        stranger = User.objects.create_user(email='stranger@test.com', password='pass123')
        assert project.get_member_role(stranger) is None

    def test_unique_slug_generation(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        user = User.objects.create_user(email='test@test.com', password='pass123')
        p1 = Project.objects.create(name='Test Project', owner=user)
        p2 = Project.objects.create(name='Test Project', owner=user)
        assert p1.slug != p2.slug
        assert p2.slug == 'test-project-1'


@pytest.mark.django_db
class TestIndexedFileModel:
    def test_indexed_file_creation(self, project):
        from apps.intelligence.models import IndexedFile
        from django.utils import timezone
        indexed = IndexedFile.objects.create(
            project=project,
            file_path='apps/test/views.py',
            file_hash='abc123',
            last_indexed=timezone.now(),
            functions_count=5,
            classes_count=2,
        )
        assert indexed.file_path == 'apps/test/views.py'
        assert indexed.total_entities == 7

    def test_total_entities_property(self, project):
        from apps.intelligence.models import IndexedFile
        from django.utils import timezone
        indexed = IndexedFile.objects.create(
            project=project,
            file_path='test.py',
            file_hash='hash',
            last_indexed=timezone.now(),
            functions_count=10,
            classes_count=5,
            endpoints_count=3,
            signals_count=2,
            crons_count=1,
        )
        assert indexed.total_entities == 21

    def test_indexed_file_unique_together(self, project):
        from apps.intelligence.models import IndexedFile
        from django.utils import timezone
        from django.db import IntegrityError
        IndexedFile.objects.create(
            project=project,
            file_path='test.py',
            file_hash='hash1',
            last_indexed=timezone.now(),
        )
        with pytest.raises(IntegrityError):
            IndexedFile.objects.create(
                project=project,
                file_path='test.py',
                file_hash='hash2',
                last_indexed=timezone.now(),
            )


@pytest.mark.django_db
class TestIngestionJobModel:
    def test_progress_percent(self):
        from apps.intelligence.models import IngestionJob
        job = IngestionJob(files_total=100, files_processed=42)
        assert job.progress_percent == 42

    def test_progress_percent_zero_total(self):
        from apps.intelligence.models import IngestionJob
        job = IngestionJob(files_total=0, files_processed=0)
        assert job.progress_percent == 0

    def test_duration_seconds(self):
        from apps.intelligence.models import IngestionJob
        now = timezone.now()
        job = IngestionJob(
            started_at=now - timezone.timedelta(seconds=30),
            completed_at=now,
        )
        assert job.duration_seconds == pytest.approx(30, abs=1)

    def test_duration_seconds_none_when_incomplete(self):
        from apps.intelligence.models import IngestionJob
        job = IngestionJob(completed_at=None)
        assert job.duration_seconds is None

    def test_ingestion_job_status_choices(self, project):
        from apps.intelligence.models import IngestionJob
        job = IngestionJob.objects.create(project=project)
        assert job.status == 'pending'
        job.status = 'running'
        job.save()
        assert job.status == 'running'

    def test_ingestion_job_trigger_choices(self, project):
        from apps.intelligence.models import IngestionJob
        job = IngestionJob.objects.create(project=project, trigger='manual')
        assert job.trigger == 'manual'
        assert job.status == 'pending'


@pytest.mark.django_db
class TestQueryLogModel:
    def test_query_log_creation(self, user, project):
        from apps.intelligence.models import QueryLog
        log = QueryLog.objects.create(
            project=project,
            user=user,
            question='How does auth work?',
            answer='Auth is handled through JWT tokens.',
            effort_level='medium',
        )
        assert log.question == 'How does auth work?'
        assert log.project == project
        assert log.user == user

    def test_query_log_effort_levels(self, project):
        from apps.intelligence.models import QueryLog
        for effort in ['low', 'medium', 'high']:
            log = QueryLog.objects.create(
                project=project,
                question=f'Test {effort}',
                answer='Answer',
                effort_level=effort,
            )
            assert log.effort_level == effort

    def test_query_log_context_files(self, project):
        from apps.intelligence.models import QueryLog
        log = QueryLog.objects.create(
            project=project,
            question='Test',
            answer='Answer',
            context_files=['file1.py', 'file2.py'],
        )
        assert log.context_files == ['file1.py', 'file2.py']

    def test_query_log_tokens_and_latency(self, project):
        from apps.intelligence.models import QueryLog
        log = QueryLog.objects.create(
            project=project,
            question='Test',
            answer='Answer',
            tokens_used=150,
            latency_ms=2500,
        )
        assert log.tokens_used == 150
        assert log.latency_ms == 2500
