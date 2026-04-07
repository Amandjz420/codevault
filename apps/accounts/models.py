import hashlib
import secrets
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Custom manager for email-based User model (no username)."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom User model using email as the primary identifier."""
    username = None  # Remove username field
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # GitHub OAuth
    github_id = models.CharField(max_length=50, blank=True)
    github_username = models.CharField(max_length=100, blank=True)
    github_access_token = models.TextField(blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email

    @property
    def display_name(self):
        return self.name or self.email.split('@')[0]


class APIToken(models.Model):
    """API tokens for MCP server authentication."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_tokens')
    name = models.CharField(max_length=255, help_text='Friendly name for this token')
    token_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=8, help_text='First 8 chars of token for display')
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'accounts_api_token'
        verbose_name = 'API Token'
        verbose_name_plural = 'API Tokens'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.prefix}...)"

    @classmethod
    def generate(cls, user, name):
        """Generate a new API token, return the plain-text token once."""
        raw_token = secrets.token_urlsafe(40)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        prefix = raw_token[:8]
        instance = cls.objects.create(
            user=user,
            name=name,
            token_hash=token_hash,
            prefix=prefix,
        )
        return instance, raw_token

    @classmethod
    def verify(cls, raw_token):
        """Verify a raw token and return the matching APIToken or None."""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        try:
            token = cls.objects.select_related('user').get(
                token_hash=token_hash,
                is_active=True,
            )
            from django.utils import timezone
            if token.expires_at and token.expires_at < timezone.now():
                return None
            token.last_used = timezone.now()
            token.save(update_fields=['last_used'])
            return token
        except cls.DoesNotExist:
            return None
