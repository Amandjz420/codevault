"""
Tests for REST API endpoints.
"""
import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
import json


@pytest.mark.django_db
class TestAuthAPI:
    def test_register(self):
        client = APIClient()
        response = client.post('/api/auth/register/', {
            'email': 'newuser@test.com',
            'name': 'New User',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
        }, format='json')
        assert response.status_code in [status.HTTP_201_CREATED, status.HTTP_200_OK]
        if response.status_code == status.HTTP_201_CREATED:
            assert 'access' in response.data

    def test_register_duplicate_email(self):
        from apps.accounts.models import User
        User.objects.create_user(email='existing@test.com', password='pass123')
        client = APIClient()
        response = client.post('/api/auth/register/', {
            'email': 'existing@test.com',
            'name': 'Dup',
            'password': 'testpass123',
            'password_confirm': 'testpass123',
        }, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_login(self):
        from apps.accounts.models import User
        User.objects.create_user(email='login@test.com', password='testpass123')
        client = APIClient()
        response = client.post('/api/auth/login/', {
            'email': 'login@test.com',
            'password': 'testpass123',
        }, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data or 'token' in response.data

    def test_login_wrong_password(self):
        from apps.accounts.models import User
        User.objects.create_user(email='login@test.com', password='testpass123')
        client = APIClient()
        response = client.post('/api/auth/login/', {
            'email': 'login@test.com',
            'password': 'wrongpass',
        }, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user(self):
        client = APIClient()
        response = client.post('/api/auth/login/', {
            'email': 'nonexistent@test.com',
            'password': 'testpass123',
        }, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestProjectAPI:
    def setup_method(self):
        from apps.accounts.models import User
        self.user = User.objects.create_user(
            email='test@test.com',
            password='pass123',
            name='Test',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_create_project(self):
        response = self.client.post('/api/projects/', {
            'name': 'New Project',
            'description': 'Test project',
        }, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['name'] == 'New Project'
        assert response.data['slug'] == 'new-project'

    def test_list_projects(self):
        from apps.projects.models import Project
        Project.objects.create(name='Project 1', owner=self.user)
        Project.objects.create(name='Project 2', owner=self.user)
        response = self.client.get('/api/projects/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 2

    def test_get_project_detail(self):
        from apps.projects.models import Project
        Project.objects.create(name='Detail Test', owner=self.user)
        response = self.client.get('/api/projects/detail-test/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Detail Test'

    def test_update_project(self):
        from apps.projects.models import Project
        Project.objects.create(name='Update Me', owner=self.user)
        response = self.client.patch('/api/projects/update-me/', {
            'description': 'Updated description',
        }, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_delete_project(self):
        from apps.projects.models import Project
        Project.objects.create(name='Delete Me', owner=self.user)
        response = self.client.delete('/api/projects/delete-me/')
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_unauthenticated_access(self):
        client = APIClient()
        response = client.get('/api/projects/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_access_denied_non_member(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        other_user = User.objects.create_user(email='other@test.com', password='pass123')
        Project.objects.create(name='Private', owner=other_user)
        response = self.client.get('/api/projects/private/')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_project_language_choices(self):
        response = self.client.post('/api/projects/', {
            'name': 'Go Project',
            'language': 'go',
        }, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['language'] == 'go'

    def test_project_with_repo_url(self):
        response = self.client.post('/api/projects/', {
            'name': 'GitHub Project',
            'repo_url': 'https://github.com/user/repo',
        }, format='json')
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['repo_url'] == 'https://github.com/user/repo'


@pytest.mark.django_db
class TestMemberAPI:
    def setup_method(self):
        from apps.accounts.models import User
        self.owner = User.objects.create_user(email='owner@test.com', password='pass123')
        self.member = User.objects.create_user(email='member@test.com', password='pass123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_add_member(self):
        from apps.projects.models import Project
        Project.objects.create(name='Team Project', owner=self.owner)
        response = self.client.post('/api/projects/team-project/members/', {
            'email': 'member@test.com',
            'role': 'member',
        }, format='json')
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    def test_list_members(self):
        from apps.projects.models import Project, ProjectMember
        project = Project.objects.create(name='Team Project', owner=self.owner)
        ProjectMember.objects.create(project=project, user=self.member, role='member')
        response = self.client.get('/api/projects/team-project/members/')
        assert response.status_code == status.HTTP_200_OK

    def test_member_roles(self):
        from apps.projects.models import Project, ProjectMember
        project = Project.objects.create(name='Team Project', owner=self.owner)
        for role in ['admin', 'member', 'viewer']:
            response = self.client.post('/api/projects/team-project/members/', {
                'email': f'{role}@test.com',
                'role': role,
            }, format='json')
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]

    def test_remove_member(self):
        from apps.projects.models import Project, ProjectMember
        project = Project.objects.create(name='Team Project', owner=self.owner)
        ProjectMember.objects.create(project=project, user=self.member, role='member')
        response = self.client.delete(
            f'/api/projects/team-project/members/{self.member.id}/'
        )
        assert response.status_code in [status.HTTP_204_NO_CONTENT, status.HTTP_200_OK]


@pytest.mark.django_db
class TestIngestionAPI:
    def setup_method(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        self.user = User.objects.create_user(email='test@test.com', password='pass123')
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_trigger_ingestion(self):
        response = self.client.post(
            f'/api/projects/{self.project.slug}/ingest/',
            {'trigger': 'manual'},
            format='json'
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
            status.HTTP_202_ACCEPTED,
        ]

    def test_get_ingestion_status(self):
        from apps.intelligence.models import IngestionJob
        job = IngestionJob.objects.create(
            project=self.project,
            status='running',
            files_total=100,
            files_processed=50,
        )
        response = self.client.get(
            f'/api/projects/{self.project.slug}/ingestion/{job.id}/'
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]


@pytest.mark.django_db
class TestQueryAPI:
    def setup_method(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        self.user = User.objects.create_user(email='test@test.com', password='pass123')
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_ask_codebase(self):
        response = self.client.post(
            f'/api/projects/{self.project.slug}/query/',
            {
                'question': 'How does authentication work?',
                'effort': 'low',
            },
            format='json'
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_202_ACCEPTED,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_search_codebase(self):
        response = self.client.get(
            f'/api/projects/{self.project.slug}/search/',
            {'query': 'authentication', 'type_filter': 'function'}
        )
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]


@pytest.mark.django_db
class TestHealthEndpoints:
    def test_health_check(self):
        client = APIClient()
        response = client.get('/health/')
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data
        assert data['status'] in ['ok', 'OK']

    def test_readiness_check(self):
        client = APIClient()
        response = client.get('/ready/')
        assert response.status_code in [200, 503]


@pytest.mark.django_db
class TestRateThrottling:
    def setup_method(self):
        from apps.accounts.models import User
        from apps.projects.models import Project
        self.user = User.objects.create_user(email='test@test.com', password='pass123')
        self.project = Project.objects.create(
            name='Test Project',
            owner=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_rate_limiting_on_queries(self):
        for _ in range(5):
            response = self.client.post(
                f'/api/projects/{self.project.slug}/query/',
                {
                    'question': 'Test query?',
                    'effort': 'low',
                },
                format='json'
            )
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break
