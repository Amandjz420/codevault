from rest_framework import serializers
from apps.accounts.serializers import UserSerializer
from .models import Project, ProjectMember


class ProjectMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = ProjectMember
        fields = ('id', 'user', 'user_id', 'role', 'joined_at')
        read_only_fields = ('id', 'joined_at')


class ProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    member_count = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id', 'name', 'slug', 'description', 'owner',
            'repo_url', 'github_repo', 'github_default_branch', 'webhook_branch',
            'local_path', 'language',
            'created_at', 'updated_at', 'last_indexed_at',
            'neo4j_namespace', 'chroma_collection',
            'is_active', 'member_count', 'user_role',
        )
        read_only_fields = (
            'id', 'slug', 'owner', 'created_at', 'updated_at',
            'last_indexed_at', 'neo4j_namespace', 'chroma_collection',
            'member_count', 'user_role',
        )

    def get_member_count(self, obj):
        return obj.project_members.count() + 1  # +1 for owner

    def get_user_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_member_role(request.user)
        return None


class ProjectCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            'name', 'description', 'repo_url',
            'github_repo', 'github_default_branch', 'webhook_branch',
            'local_path', 'language', 'github_webhook_secret',
        )

    def create(self, validated_data):
        user = self.context['request'].user
        project = Project.objects.create(owner=user, **validated_data)
        return project


class ProjectUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = (
            'name', 'description', 'repo_url',
            'github_repo', 'github_default_branch', 'webhook_branch',
            'local_path', 'language', 'github_webhook_secret',
        )


class ProjectMemberCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=['admin', 'member', 'viewer'], default='member')

    def validate_email(self, value):
        from apps.accounts.models import User
        try:
            self.user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError(f"No user with email {value!r}.")
        return value
