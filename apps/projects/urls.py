from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMemberListView,
    ProjectMemberDetailView,
)

urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='project-list'),
    path('<slug:slug>/', ProjectDetailView.as_view(), name='project-detail'),
    path('<slug:slug>/members/', ProjectMemberListView.as_view(), name='project-members'),
    path('<slug:slug>/members/<int:pk>/', ProjectMemberDetailView.as_view(), name='project-member-detail'),
]
