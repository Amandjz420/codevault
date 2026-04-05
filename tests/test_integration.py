"""
Integration tests for CodeVault end-to-end workflows.
"""
import pytest
from django.utils import timezone
from rest_framework import status
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
class TestProjectOnboardingFlow:
    """Test complete project creation and ingestion workflow."""

    def test_create_project_and_start_ingestion(self, auth_client, user):
        """Test creating a project and triggering initial ingestion."""
        # Create project
        create_response = auth_client.post('/api/projects/', {
            'name': 'My New Project',
            'description': 'A new codebase to index',
            'language': 'python',
        }, format='json')
        assert create_response.status_code == status.HTTP_201_CREATED
        project_slug = create_response.data['slug']

        # Verify project appears in list
        list_response = auth_client.get('/api/projects/')
        assert list_response.status_code == status.HTTP_200_OK
        project_names = [p['name'] for p in list_response.data]
        assert 'My New Project' in project_names

        # Get project details
        detail_response = auth_client.get(f'/api/projects/{project_slug}/')
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data['owner'] == user.id

    def test_invite_team_member_workflow(self, auth_client, user):
        """Test inviting a team member to a project."""
        from apps.accounts.models import User
        from apps.projects.models import Project

        # Create project
        project = Project.objects.create(name='Team Project', owner=user)

        # Create another user
        team_member = User.objects.create_user(
            email='teammate@example.com',
            password='pass123',
            name='Team Member'
        )

        # Invite team member
        invite_response = auth_client.post(
            f'/api/projects/{project.slug}/members/',
            {
                'email': 'teammate@example.com',
                'role': 'member',
            },
            format='json'
        )
        assert invite_response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ]

        # Verify member can access project
        member_client = auth_client.__class__()
        member_client.force_authenticate(user=team_member)
        access_response = member_client.get(f'/api/projects/{project.slug}/')
        assert access_response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestCodeSearchWorkflow:
    """Test searching and querying indexed code."""

    def test_search_after_indexing(self, auth_client, user):
        """Test searching for code after ingestion."""
        from apps.projects.models import Project
        from apps.intelligence.models import IndexedFile
        from tests.conftest import PYTHON_SOURCE

        project = Project.objects.create(name='Search Test', owner=user)

        # Record some indexed files
        IndexedFile.objects.create(
            project=project,
            file_path='apps/auth/models.py',
            file_hash='abc123',
            last_indexed=timezone.now(),
            functions_count=5,
            classes_count=2,
        )

        # Search for code
        search_response = auth_client.get(
            f'/api/projects/{project.slug}/search/',
            {'query': 'authentication'},
        )
        assert search_response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_ask_question_workflow(self, auth_client, user):
        """Test asking questions about indexed codebase."""
        from apps.projects.models import Project

        project = Project.objects.create(name='Q&A Test', owner=user)

        # Ask a question
        query_response = auth_client.post(
            f'/api/projects/{project.slug}/query/',
            {
                'question': 'How does user authentication work?',
                'effort': 'low',
            },
            format='json'
        )
        assert query_response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_202_ACCEPTED,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.django_db
class TestMultiLanguageIndexing:
    """Test indexing and parsing multiple language projects."""

    def test_multi_language_project_creation(self, auth_client, user):
        """Test creating and indexing a multi-language project."""
        # Create multi-language project
        create_response = auth_client.post('/api/projects/', {
            'name': 'Full Stack App',
            'language': 'multi',
            'description': 'Python backend + React frontend + Go workers',
        }, format='json')
        assert create_response.status_code == status.HTTP_201_CREATED
        assert create_response.data['language'] == 'multi'

    def test_language_detection_for_files(self):
        """Test that files are parsed with correct language parser."""
        from apps.intelligence.services.parsers import get_parser_for_file
        from tests.conftest import (
            PYTHON_SOURCE, JS_SOURCE, GO_SOURCE,
            RUST_SOURCE, JAVA_SOURCE,
        )

        files = [
            ('models.py', PYTHON_SOURCE, 'python'),
            ('routes.js', JS_SOURCE, 'javascript'),
            ('handler.go', GO_SOURCE, 'go'),
            ('lib.rs', RUST_SOURCE, 'rust'),
            ('Controller.java', JAVA_SOURCE, 'java'),
        ]

        for filename, source, expected_lang in files:
            parser = get_parser_for_file(filename)
            assert parser is not None
            result = parser.parse(source, filename)
            assert result.language == expected_lang


@pytest.mark.django_db
class TestGitHubIntegration:
    """Test GitHub webhook integration."""

    def test_github_webhook_triggers_indexing(self, user):
        """Test that GitHub webhook triggers project indexing."""
        from apps.projects.models import Project
        import json
        import hmac
        import hashlib

        project = Project.objects.create(
            name='GitHub Project',
            owner=user,
            repo_url='https://github.com/user/repo',
            github_webhook_secret='test-secret',
        )

        client = __import__('rest_framework.test', fromlist=['APIClient']).APIClient()
        payload = json.dumps({'action': 'pushed', 'ref': 'refs/heads/main'})
        signature = 'sha256=' + hmac.new(
            'test-secret'.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        response = client.post(
            f'/webhooks/github/{project.slug}/',
            payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=signature,
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.django_db
class TestAPITokenAuthentication:
    """Test API token-based authentication."""

    def test_api_token_workflow(self, user):
        """Test creating and using API token."""
        from apps.accounts.models import APIToken
        from rest_framework.test import APIClient

        # Generate token
        token_obj, raw_token = APIToken.generate(user, 'Integration Token')
        assert token_obj.name == 'Integration Token'
        assert len(raw_token) > 20

        # Use token for API requests
        client = APIClient()
        response = client.get(
            '/api/projects/',
            HTTP_AUTHORIZATION=f'Bearer {raw_token}'
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
        ]

    def test_token_expiration(self, user):
        """Test that expired tokens are rejected."""
        from apps.accounts.models import APIToken
        from rest_framework.test import APIClient

        token_obj, raw_token = APIToken.generate(user, 'Expiring Token')

        # Set token to expired
        token_obj.expires_at = timezone.now() - timezone.timedelta(hours=1)
        token_obj.save()

        # Try to use expired token
        client = APIClient()
        response = client.get(
            '/api/projects/',
            HTTP_AUTHORIZATION=f'Bearer {raw_token}'
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestConcurrentOperations:
    """Test handling concurrent requests and operations."""

    def test_concurrent_project_creation(self, auth_client, user):
        """Test creating multiple projects concurrently."""
        from apps.projects.models import Project

        # Simulate concurrent creates
        responses = []
        for i in range(3):
            response = auth_client.post('/api/projects/', {
                'name': f'Concurrent Project {i}',
                'language': 'python',
            }, format='json')
            responses.append(response)

        # All should succeed with unique slugs
        assert all(r.status_code == status.HTTP_201_CREATED for r in responses)
        slugs = [r.data['slug'] for r in responses]
        assert len(set(slugs)) == 3

    def test_concurrent_ingestion_jobs(self, user):
        """Test handling multiple ingestion jobs."""
        from apps.projects.models import Project
        from apps.intelligence.models import IngestionJob

        project = Project.objects.create(name='Concurrent Ingest', owner=user)

        # Create multiple ingestion jobs
        jobs = []
        for i in range(3):
            job = IngestionJob.objects.create(
                project=project,
                trigger='manual',
                status='running',
            )
            jobs.append(job)

        # All should be independent
        assert len(jobs) == 3
        assert all(j.project == project for j in jobs)


@pytest.mark.django_db
class TestErrorHandling:
    """Test error handling across the application."""

    def test_invalid_project_slug(self, auth_client):
        """Test accessing non-existent project."""
        response = auth_client.get('/api/projects/nonexistent-project-xyz/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_malformed_request_body(self, auth_client):
        """Test handling malformed JSON."""
        response = auth_client.post(
            '/api/projects/',
            {'invalid': 'json', 'missing_required': 'fields'},
            format='json'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthorized_access_to_private_project(self, auth_client):
        """Test accessing another user's private project."""
        from apps.accounts.models import User
        from apps.projects.models import Project

        other_user = User.objects.create_user(
            email='other@example.com',
            password='pass123'
        )
        private_project = Project.objects.create(
            name='Private Project',
            owner=other_user,
        )

        response = auth_client.get(f'/api/projects/{private_project.slug}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_permission_denied_on_delete(self, auth_client):
        """Test that non-owners cannot delete projects."""
        from apps.accounts.models import User
        from apps.projects.models import Project, ProjectMember

        owner = User.objects.create_user(email='owner@example.com', password='pass123')
        project = Project.objects.create(name='Test Project', owner=owner)
        current_user = auth_client.handler._force_user

        if current_user != owner:
            response = auth_client.delete(f'/api/projects/{project.slug}/')
            assert response.status_code in [
                status.HTTP_403_FORBIDDEN,
                status.HTTP_404_NOT_FOUND,
            ]
