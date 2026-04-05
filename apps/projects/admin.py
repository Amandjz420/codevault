from django.contrib import admin
from .models import Project, ProjectMember


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0
    raw_id_fields = ('user', 'invited_by')
    readonly_fields = ('joined_at',)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'slug', 'owner', 'language',
        'is_active', 'last_indexed_at', 'created_at',
    )
    list_filter = ('language', 'is_active')
    search_fields = ('name', 'slug', 'owner__email', 'description')
    prepopulated_fields = {'slug': ('name',)}
    raw_id_fields = ('owner',)
    readonly_fields = ('created_at', 'updated_at', 'last_indexed_at', 'neo4j_namespace', 'chroma_collection')
    inlines = [ProjectMemberInline]
    ordering = ('-created_at',)
    fieldsets = (
        (None, {'fields': ('name', 'slug', 'description', 'owner', 'language', 'is_active')}),
        ('Repository', {'fields': ('repo_url', 'local_path', 'github_webhook_secret')}),
        ('Storage', {'fields': ('neo4j_namespace', 'chroma_collection')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'last_indexed_at')}),
    )


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'project', 'role', 'joined_at')
    list_filter = ('role',)
    search_fields = ('user__email', 'project__name')
    raw_id_fields = ('user', 'project', 'invited_by')
    readonly_fields = ('joined_at',)
