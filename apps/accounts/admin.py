from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, APIToken


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('name', 'first_name', 'last_name')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'name', 'password1', 'password2'),
        }),
    )
    list_display = ('email', 'name', 'is_staff', 'is_active', 'created_at')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'prefix', 'is_active', 'created_at', 'last_used')
    list_filter = ('is_active',)
    search_fields = ('name', 'user__email', 'prefix')
    readonly_fields = ('token_hash', 'prefix', 'created_at', 'last_used')
    raw_id_fields = ('user',)
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False  # Tokens must be created via API
