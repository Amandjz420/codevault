import secrets
from django.db import models


class OAuthClient(models.Model):
    """A dynamically-registered MCP OAuth 2.0 client."""
    client_id = models.CharField(max_length=64, unique=True)
    client_secret = models.CharField(max_length=64, blank=True)
    client_name = models.CharField(max_length=255, blank=True)
    redirect_uris = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'mcp_oauth_client'

    def __str__(self):
        return f"{self.client_name or self.client_id}"


class OAuthAuthorizationCode(models.Model):
    """Short-lived authorization code (10-minute TTL) for the OAuth code flow."""
    code = models.CharField(max_length=128, unique=True)
    client = models.ForeignKey(OAuthClient, on_delete=models.CASCADE)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    redirect_uri = models.URLField(max_length=500)
    code_challenge = models.CharField(max_length=128, blank=True)
    code_challenge_method = models.CharField(max_length=10, blank=True, default='S256')
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        db_table = 'mcp_oauth_authorization_code'
        indexes = [
            models.Index(fields=['code']),
        ]

    def __str__(self):
        return f"code for {self.user} via {self.client}"
