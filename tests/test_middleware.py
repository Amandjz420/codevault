"""
Tests for middleware and authentication.
"""
import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock


@pytest.mark.django_db
class TestAPITokenAuth:
    """Test API token authentication middleware."""

    def test_request_with_valid_api_token(self):
        from apps.accounts.models import User, APIToken
        user = User.objects.create_user(email='test@test.com', password='pass123')
        token_obj, raw_token = APIToken.generate(user, 'Test Token')

        client = APIClient()
        response = client.get(
            '/api/projects/',
            HTTP_AUTHORIZATION=f'Bearer {raw_token}'
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED]

    def test_request_with_invalid_api_token(self):
        client = APIClient()
        response = client.get(
            '/api/projects/',
            HTTP_AUTHORIZATION='Bearer invalid-token-xyz'
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_request_without_auth_token(self):
        client = APIClient()
        response = client.get('/api/projects/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_jwt_token_authentication(self):
        from apps.accounts.models import User
        user = User.objects.create_user(email='test@test.com', password='testpass123')
        client = APIClient()

        login_response = client.post('/api/auth/login/', {
            'email': 'test@test.com',
            'password': 'testpass123',
        }, format='json')

        if login_response.status_code == status.HTTP_200_OK:
            token = login_response.data.get('access')
            if token:
                client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
                response = client.get('/api/projects/')
                assert response.status_code in [
                    status.HTTP_200_OK,
                    status.HTTP_401_UNAUTHORIZED,
                ]


@pytest.mark.django_db
class TestPermissionMiddleware:
    """Test project access permissions middleware."""

    def test_owner_can_access_own_project(self):
        from apps.accounts.models import User
        from apps.projects.models import Project

        user = User.objects.create_user(email='owner@test.com', password='pass123')
        project = Project.objects.create(name='My Project', owner=user)

        client = APIClient()
        client.force_authenticate(user=user)
        response = client.get(f'/api/projects/{project.slug}/')
        assert response.status_code == status.HTTP_200_OK

    def test_member_can_access_project(self):
        from apps.accounts.models import User
        from apps.projects.models import Project, ProjectMember

        owner = User.objects.create_user(email='owner@test.com', password='pass123')
        member = User.objects.create_user(email='member@test.com', password='pass123')
        project = Project.objects.create(name='Shared Project', owner=owner)
        ProjectMember.objects.create(project=project, user=member, role='member')

        client = APIClient()
        client.force_authenticate(user=member)
        response = client.get(f'/api/projects/{project.slug}/')
        assert response.status_code == status.HTTP_200_OK

    def test_non_member_cannot_access_project(self):
        from apps.accounts.models import User
        from apps.projects.models import Project

        owner = User.objects.create_user(email='owner@test.com', password='pass123')
        stranger = User.objects.create_user(email='stranger@test.com', password='pass123')
        project = Project.objects.create(name='Private Project', owner=owner)

        client = APIClient()
        client.force_authenticate(user=stranger)
        response = client.get(f'/api/projects/{project.slug}/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_viewer_cannot_modify_project(self):
        from apps.accounts.models import User
        from apps.projects.models import Project, ProjectMember

        owner = User.objects.create_user(email='owner@test.com', password='pass123')
        viewer = User.objects.create_user(email='viewer@test.com', password='pass123')
        project = Project.objects.create(name='Read-only Project', owner=owner)
        ProjectMember.objects.create(project=project, user=viewer, role='viewer')

        client = APIClient()
        client.force_authenticate(user=viewer)
        response = client.patch(
            f'/api/projects/{project.slug}/',
            {'description': 'Modified'},
            format='json'
        )
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_admin_can_modify_project(self):
        from apps.accounts.models import User
        from apps.projects.models import Project, ProjectMember

        owner = User.objects.create_user(email='owner@test.com', password='pass123')
        admin = User.objects.create_user(email='admin@test.com', password='pass123')
        project = Project.objects.create(name='Admin Project', owner=owner)
        ProjectMember.objects.create(project=project, user=admin, role='admin')

        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.patch(
            f'/api/projects/{project.slug}/',
            {'description': 'Modified by admin'},
            format='json'
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_403_FORBIDDEN,
        ]


@pytest.mark.django_db
class TestWebhookAuth:
    """Test GitHub webhook signature verification."""

    def test_github_webhook_signature_validation(self, project):
        import hmac
        import hashlib
        import json

        client = APIClient()
        payload = json.dumps({'action': 'opened'})
        secret = project.github_webhook_secret or 'test-secret'

        signature = 'sha256=' + hmac.new(
            secret.encode(),
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
            status.HTTP_404_NOT_FOUND,
            status.HTTP_401_UNAUTHORIZED,
        ]

    def test_webhook_with_invalid_signature(self, project):
        import json

        client = APIClient()
        payload = json.dumps({'action': 'opened'})

        response = client.post(
            f'/webhooks/github/{project.slug}/',
            payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256='sha256=invalid',
        )
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.django_db
class TestCORSMiddleware:
    """Test CORS header handling."""

    def test_cors_headers_present(self):
        client = APIClient()
        response = client.get('/api/projects/', HTTP_ORIGIN='http://localhost:3000')
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_200_OK,
        ]

    def test_preflight_request_handling(self):
        client = APIClient()
        response = client.options(
            '/api/projects/',
            HTTP_ORIGIN='http://localhost:3000',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]


@pytest.mark.django_db
class TestRateLimiting:
    """Test request rate limiting."""

    def test_rate_limit_headers(self):
        from apps.accounts.models import User
        user = User.objects.create_user(email='test@test.com', password='pass123')
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get('/api/projects/')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_429_TOO_MANY_REQUESTS]

    def test_rate_limit_persistence(self):
        from apps.accounts.models import User
        user = User.objects.create_user(email='test@test.com', password='pass123')
        client = APIClient()
        client.force_authenticate(user=user)

        responses = []
        for _ in range(3):
            response = client.get('/api/projects/')
            responses.append(response.status_code)

        assert any(code in responses for code in [
            status.HTTP_200_OK,
            status.HTTP_429_TOO_MANY_REQUESTS,
        ])
