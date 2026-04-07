from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMemberListCreateView,
    ProjectMemberDetailView,
    GraphStatsView,
    GraphFilesView,
    GraphFunctionsView,
    GraphEndpointsView,
    GraphModelsView,
    GraphClassesView,
    QueryView,
    IngestionJobListView,
    TriggerIngestionView,
    TriggerGithubIngestionView,
    ListGithubReposView,
    ListGithubRepoBranchesView,
    QueryLogListView,
)
from .webhooks import github_webhook

urlpatterns = [
    # Projects CRUD
    path('projects/', ProjectListCreateView.as_view(), name='project-list'),
    path('projects/<slug:slug>/', ProjectDetailView.as_view(), name='project-detail'),

    # Members
    path('projects/<slug:slug>/members/', ProjectMemberListCreateView.as_view(), name='project-member-list'),
    path('projects/<slug:slug>/members/<int:pk>/', ProjectMemberDetailView.as_view(), name='project-member-detail'),

    # Intelligence / Graph
    path('projects/<slug:slug>/stats/', GraphStatsView.as_view(), name='project-stats'),
    path('projects/<slug:slug>/files/', GraphFilesView.as_view(), name='project-files'),
    path('projects/<slug:slug>/functions/', GraphFunctionsView.as_view(), name='project-functions'),
    path('projects/<slug:slug>/endpoints/', GraphEndpointsView.as_view(), name='project-endpoints'),
    path('projects/<slug:slug>/models/', GraphModelsView.as_view(), name='project-models'),
    path('projects/<slug:slug>/classes/', GraphClassesView.as_view(), name='project-classes'),

    # Query
    path('projects/<slug:slug>/query/', QueryView.as_view(), name='project-query'),
    path('projects/<slug:slug>/query-logs/', QueryLogListView.as_view(), name='project-query-logs'),

    # Ingestion
    path('projects/<slug:slug>/ingest/', TriggerIngestionView.as_view(), name='project-ingest'),
    path('projects/<slug:slug>/ingest/github/', TriggerGithubIngestionView.as_view(), name='project-ingest-github'),
    path('projects/<slug:slug>/jobs/', IngestionJobListView.as_view(), name='project-jobs'),

    # GitHub
    path('github/repos/', ListGithubReposView.as_view(), name='github-repos'),
    path('github/repos/<str:owner>/<str:repo>/branches/', ListGithubRepoBranchesView.as_view(), name='github-repo-branches'),

    # Webhooks
    path('webhooks/github/<slug:project_slug>/', github_webhook, name='github-webhook'),
]
