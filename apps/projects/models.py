from django.db import models
from django.utils.text import slugify
import logging

logger = logging.getLogger(__name__)


class Project(models.Model):
    """A codebase project to be indexed by CodeVault."""

    LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
        ('typescript', 'TypeScript'),
        ('go', 'Go'),
        ('rust', 'Rust'),
        ('java', 'Java'),
        ('multi', 'Multi-language'),
    ]

    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, max_length=100)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='owned_projects',
    )
    members = models.ManyToManyField(
        'accounts.User',
        through='ProjectMember',
        through_fields=('project', 'user'),
        related_name='projects',
        blank=True,
    )
    repo_url = models.URLField(blank=True, help_text='GitHub/GitLab repository URL')
    github_repo = models.CharField(
        max_length=200,
        blank=True,
        help_text='GitHub repo in owner/repo format, e.g. acme/my-service',
    )
    github_default_branch = models.CharField(max_length=100, default='main')
    github_webhook_secret = models.CharField(
        max_length=255,
        blank=True,
        help_text='HMAC secret for verifying GitHub webhooks',
    )
    local_path = models.CharField(
        max_length=500,
        blank=True,
        help_text='Absolute path to local project directory',
    )
    language = models.CharField(
        max_length=50,
        choices=LANGUAGE_CHOICES,
        default='python',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_indexed_at = models.DateTimeField(null=True, blank=True)
    neo4j_namespace = models.CharField(
        max_length=100,
        blank=True,
        help_text='Namespace for scoping graph queries (defaults to slug)',
    )
    chroma_collection = models.CharField(
        max_length=100,
        blank=True,
        help_text='ChromaDB collection name (defaults to slug)',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'projects_project'
        verbose_name = 'Project'
        verbose_name_plural = 'Projects'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Project.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if not self.neo4j_namespace:
            self.neo4j_namespace = self.slug

        if not self.chroma_collection:
            # ChromaDB collection names must be 3-63 chars, no special chars
            safe_name = self.slug.replace('-', '_')
            self.chroma_collection = f"cv_{safe_name}"[:63]

        super().save(*args, **kwargs)

    def get_member_role(self, user):
        """Return user's role in this project, or None if not a member."""
        if self.owner_id == user.pk:
            return 'owner'
        try:
            member = ProjectMember.objects.get(project=self, user=user)
            return member.role
        except ProjectMember.DoesNotExist:
            return None

    def user_has_access(self, user):
        return self.owner_id == user.pk or ProjectMember.objects.filter(
            project=self, user=user
        ).exists()

    def user_can_write(self, user):
        if self.owner_id == user.pk:
            return True
        try:
            member = ProjectMember.objects.get(project=self, user=user)
            return member.role in ('admin', 'member')
        except ProjectMember.DoesNotExist:
            return False

    def hard_delete(self, *args, **kwargs):
        """Hard delete project and clean up all related data."""
        # Clean Neo4j graph nodes
        try:
            from apps.intelligence.services.graph import GraphService
            graph = GraphService(self.neo4j_namespace)
            graph.clear_project()
            graph.close()
        except Exception as e:
            logger.warning(f"[Project.hard_delete] Neo4j cleanup failed for {self.slug}: {e}")

        # Clean ChromaDB collection
        try:
            from apps.intelligence.services.vector import VectorService
            vector = VectorService(self.chroma_collection)
            vector.delete_collection()
        except Exception as e:
            logger.warning(f"[Project.hard_delete] ChromaDB cleanup failed for {self.slug}: {e}")

        # Clean Postgres records (IndexedFile, IngestionJob, QueryLog, ProjectMemory)
        self.indexed_files.all().delete()
        
        # Perform actual hard delete
        super().delete(*args, **kwargs)


class ProjectMember(models.Model):
    """Through model for Project-User membership."""

    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='project_members',
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='project_memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)
    invited_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitations_sent',
    )

    class Meta:
        db_table = 'projects_member'
        verbose_name = 'Project Member'
        verbose_name_plural = 'Project Members'
        unique_together = ('project', 'user')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.email} — {self.project.name} ({self.role})"
