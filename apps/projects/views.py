from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from .models import Project, ProjectMember
from .serializers import (
    ProjectSerializer,
    ProjectCreateSerializer,
    ProjectUpdateSerializer,
    ProjectMemberSerializer,
    ProjectMemberCreateSerializer,
)


class ProjectListCreateView(APIView):
    """GET/POST /api/projects/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Q
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(project_members__user=request.user),
            is_active=True
        ).distinct().select_related('owner')
        return Response(ProjectSerializer(projects, many=True, context={'request': request}).data)

    def post(self, request):
        serializer = ProjectCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        project = serializer.save()
        return Response(
            ProjectSerializer(project, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProjectDetailView(APIView):
    """GET/PATCH/DELETE /api/projects/<slug>/"""
    permission_classes = [IsAuthenticated]

    def _get_project(self, slug, user, require_write=False):
        project = get_object_or_404(Project, slug=slug, is_active=True)
        if not project.user_has_access(user):
            return None, Response({'error': 'Project not found or access denied.'}, status=status.HTTP_404_NOT_FOUND)
        if require_write and not project.user_can_write(user):
            return None, Response({'error': 'You do not have write access to this project.'}, status=status.HTTP_403_FORBIDDEN)
        return project, None

    def get(self, request, slug):
        project, err = self._get_project(slug, request.user)
        if err:
            return err
        return Response(ProjectSerializer(project, context={'request': request}).data)

    def patch(self, request, slug):
        project, err = self._get_project(slug, request.user, require_write=True)
        if err:
            return err
        serializer = ProjectUpdateSerializer(project, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(ProjectSerializer(project, context={'request': request}).data)

    def delete(self, request, slug):
        project = get_object_or_404(Project, slug=slug)
        if project.owner != request.user:
            return Response({'error': 'Only the project owner can delete it.'}, status=status.HTTP_403_FORBIDDEN)
        project.is_active = False
        project.save(update_fields=['is_active'])
        return Response({'message': 'Project deleted.'}, status=status.HTTP_204_NO_CONTENT)


class ProjectMemberListView(APIView):
    """GET/POST /api/projects/<slug>/members/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        project = get_object_or_404(Project, slug=slug, is_active=True)
        if not project.user_has_access(request.user):
            return Response({'error': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)
        members = project.project_members.select_related('user')
        return Response(ProjectMemberSerializer(members, many=True).data)

    def post(self, request, slug):
        project = get_object_or_404(Project, slug=slug, is_active=True)
        if not project.user_can_write(request.user):
            return Response({'error': 'Write access required.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectMemberCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.user
        if project.owner == user:
            return Response({'error': 'User is already the project owner.'}, status=status.HTTP_400_BAD_REQUEST)

        member, created = ProjectMember.objects.get_or_create(
            project=project,
            user=user,
            defaults={
                'role': serializer.validated_data['role'],
                'invited_by': request.user,
            }
        )
        if not created:
            member.role = serializer.validated_data['role']
            member.save(update_fields=['role'])

        return Response(
            ProjectMemberSerializer(member).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ProjectMemberDetailView(APIView):
    """PATCH/DELETE /api/projects/<slug>/members/<pk>/"""
    permission_classes = [IsAuthenticated]

    def patch(self, request, slug, pk):
        project = get_object_or_404(Project, slug=slug, is_active=True)
        if not project.user_can_write(request.user):
            return Response({'error': 'Write access required.'}, status=status.HTTP_403_FORBIDDEN)
        member = get_object_or_404(ProjectMember, pk=pk, project=project)
        role = request.data.get('role')
        if role not in ('admin', 'member', 'viewer'):
            return Response({'error': 'Invalid role.'}, status=status.HTTP_400_BAD_REQUEST)
        member.role = role
        member.save(update_fields=['role'])
        return Response(ProjectMemberSerializer(member).data)

    def delete(self, request, slug, pk):
        project = get_object_or_404(Project, slug=slug, is_active=True)
        if not project.user_can_write(request.user):
            return Response({'error': 'Write access required.'}, status=status.HTTP_403_FORBIDDEN)
        member = get_object_or_404(ProjectMember, pk=pk, project=project)
        if member.user == project.owner:
            return Response({'error': 'Cannot remove the project owner.'}, status=status.HTTP_400_BAD_REQUEST)
        member.delete()
        return Response({'message': 'Member removed.'}, status=status.HTTP_204_NO_CONTENT)
