"""
MCP OAuth 2.0 Authorization Server views.

Implements the OAuth 2.0 Authorization Code flow with PKCE as required by
the MCP Authorization specification, so MCP clients (Claude Desktop, Cursor,
etc.) can authenticate without a pre-configured Bearer token.

Endpoints:
  GET  /.well-known/oauth-authorization-server  — discovery metadata
  POST /mcp/oauth/register/                     — dynamic client registration
  GET  /mcp/oauth/authorize/                    — login form
  POST /mcp/oauth/authorize/                    — credential validation + code redirect
  POST /mcp/oauth/token/                        — code → access token exchange
"""
import base64
import hashlib
import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)


def _base_url(request):
    scheme = 'https' if request.is_secure() else 'http'
    return f"{scheme}://{request.get_host()}"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class OAuthMetadataView(View):
    """GET /.well-known/oauth-authorization-server"""

    def get(self, request):
        base = _base_url(request)
        return JsonResponse({
            "issuer": base,
            "authorization_endpoint": f"{base}/mcp/oauth/authorize",
            "token_endpoint": f"{base}/mcp/oauth/token",
            "registration_endpoint": f"{base}/mcp/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        })


# ---------------------------------------------------------------------------
# Dynamic client registration  (RFC 7591)
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class OAuthRegisterView(View):
    """POST /mcp/oauth/register/"""

    def post(self, request):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "invalid_request"}, status=400)

        redirect_uris = data.get('redirect_uris', [])
        if not redirect_uris:
            return JsonResponse(
                {"error": "invalid_request", "error_description": "redirect_uris is required"},
                status=400,
            )

        from apps.mcp.models import OAuthClient
        client = OAuthClient.objects.create(
            client_id=secrets.token_urlsafe(32),
            client_secret=secrets.token_urlsafe(32),
            client_name=data.get('client_name', ''),
            redirect_uris=redirect_uris,
        )
        logger.info(f"[MCP OAuth] Registered client: {client.client_name or client.client_id}")

        return JsonResponse({
            "client_id": client.client_id,
            "client_secret": client.client_secret,
            "client_name": client.client_name,
            "redirect_uris": client.redirect_uris,
        }, status=201)


# ---------------------------------------------------------------------------
# Authorization endpoint  (login form)
# ---------------------------------------------------------------------------

_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Authorize — CodeVault</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0d0d0d; color: #e0e0e0;
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
    }}
    .card {{
      background: #161616; border: 1px solid #252525; border-radius: 14px;
      padding: 44px 40px; width: 100%; max-width: 420px;
    }}
    .logo {{ font-size: 22px; font-weight: 700; color: #fff; margin-bottom: 6px; }}
    .logo span {{ color: #6366f1; }}
    .subtitle {{ color: #777; font-size: 13px; margin-bottom: 28px; line-height: 1.5; }}
    .client {{ color: #a5b4fc; font-weight: 600; }}
    .scope-box {{
      background: #0d0d0d; border: 1px solid #222; border-radius: 8px;
      padding: 11px 14px; font-size: 13px; color: #888; margin-bottom: 24px;
    }}
    .scope-box strong {{ color: #b0b0b0; display: block; margin-bottom: 4px; }}
    label {{ display: block; font-size: 12px; color: #888; margin-top: 16px; margin-bottom: 5px; text-transform: uppercase; letter-spacing: .05em; }}
    input[type=email], input[type=password] {{
      width: 100%; padding: 10px 13px; background: #0d0d0d; border: 1px solid #2a2a2a;
      border-radius: 8px; color: #e0e0e0; font-size: 14px; outline: none;
      transition: border-color .15s;
    }}
    input:focus {{ border-color: #6366f1; }}
    .error {{ color: #f87171; font-size: 13px; margin-top: 14px; padding: 10px 13px; background: #1f0000; border: 1px solid #7f1d1d; border-radius: 8px; }}
    button {{
      width: 100%; padding: 12px; background: #6366f1; color: #fff; border: none;
      border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 22px;
      transition: background .15s;
    }}
    button:hover {{ background: #4f51d1; }}
    .footer {{ text-align: center; font-size: 12px; color: #555; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">Code<span>Vault</span></div>
    <p class="subtitle">
      <span class="client">{client_name}</span> is requesting access to your CodeVault account.
    </p>
    <div class="scope-box">
      <strong>Permissions requested</strong>
      Read-only access to your projects, codebase graph, and intelligence queries.
    </div>
    {error_html}
    <form method="post" action="/mcp/oauth/authorize">
      <input type="hidden" name="client_id" value="{client_id}">
      <input type="hidden" name="redirect_uri" value="{redirect_uri}">
      <input type="hidden" name="state" value="{state}">
      <input type="hidden" name="code_challenge" value="{code_challenge}">
      <input type="hidden" name="code_challenge_method" value="{code_challenge_method}">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required autofocus placeholder="you@example.com">
      <label for="password">Password</label>
      <input type="password" id="password" name="password" required placeholder="••••••••">
      <button type="submit">Authorize Access</button>
    </form>
    <p class="footer">You will be redirected back to {client_name} after signing in.</p>
  </div>
</body>
</html>"""


@method_decorator(csrf_exempt, name='dispatch')
class OAuthAuthorizeView(View):
    """
    GET  /mcp/oauth/authorize/ — render login form
    POST /mcp/oauth/authorize/ — validate credentials, issue code, redirect
    """

    def _render_form(self, *, client_name, client_id, redirect_uri,
                     state, code_challenge, code_challenge_method, error=''):
        error_html = f'<div class="error">{error}</div>' if error else ''
        html = _LOGIN_HTML.format(
            client_name=client_name,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            error_html=error_html,
        )
        return HttpResponse(html, content_type='text/html')

    def get(self, request):
        client_id = request.GET.get('client_id', '')
        redirect_uri = request.GET.get('redirect_uri', '')
        state = request.GET.get('state', '')
        code_challenge = request.GET.get('code_challenge', '')
        code_challenge_method = request.GET.get('code_challenge_method', 'S256')
        response_type = request.GET.get('response_type', 'code')

        if response_type != 'code':
            return HttpResponse('Only response_type=code is supported.', status=400)

        from apps.mcp.models import OAuthClient
        try:
            client = OAuthClient.objects.get(client_id=client_id)
        except OAuthClient.DoesNotExist:
            return HttpResponse('Unknown client_id.', status=400)

        if redirect_uri not in client.redirect_uris:
            return HttpResponse('redirect_uri is not registered for this client.', status=400)

        return self._render_form(
            client_name=client.client_name or client_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
        )

    def post(self, request):
        client_id = request.POST.get('client_id', '')
        redirect_uri = request.POST.get('redirect_uri', '')
        state = request.POST.get('state', '')
        code_challenge = request.POST.get('code_challenge', '')
        code_challenge_method = request.POST.get('code_challenge_method', 'S256')
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        from apps.mcp.models import OAuthClient
        try:
            client = OAuthClient.objects.get(client_id=client_id)
        except OAuthClient.DoesNotExist:
            return HttpResponse('Unknown client_id.', status=400)

        if redirect_uri not in client.redirect_uris:
            return HttpResponse('redirect_uri is not registered for this client.', status=400)

        # Authenticate
        from django.contrib.auth import authenticate
        user = authenticate(request, username=email, password=password)

        if user is None:
            return self._render_form(
                client_name=client.client_name or client_id,
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                error='Invalid email or password. Please try again.',
            )

        # Issue auth code
        from apps.mcp.models import OAuthAuthorizationCode
        code = secrets.token_urlsafe(32)
        OAuthAuthorizationCode.objects.create(
            code=code,
            client=client,
            user=user,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        logger.info(f"[MCP OAuth] Issued auth code for {user.email} → {client.client_name or client_id}")

        params = {'code': code}
        if state:
            params['state'] = state
        return HttpResponseRedirect(f"{redirect_uri}?{urlencode(params)}")


# ---------------------------------------------------------------------------
# Token endpoint
# ---------------------------------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class OAuthTokenView(View):
    """POST /mcp/oauth/token/"""

    def post(self, request):
        content_type = request.content_type or ''
        if 'application/json' in content_type:
            try:
                data = json.loads(request.body)
            except Exception:
                return JsonResponse({"error": "invalid_request"}, status=400)
        else:
            data = request.POST

        grant_type = data.get('grant_type', '')
        if grant_type != 'authorization_code':
            return JsonResponse({"error": "unsupported_grant_type"}, status=400)

        code_value = data.get('code', '')
        redirect_uri = data.get('redirect_uri', '')
        client_id = data.get('client_id', '')
        code_verifier = data.get('code_verifier', '')

        from apps.mcp.models import OAuthClient, OAuthAuthorizationCode

        try:
            client = OAuthClient.objects.get(client_id=client_id)
        except OAuthClient.DoesNotExist:
            return JsonResponse({"error": "invalid_client"}, status=401)

        try:
            auth_code = OAuthAuthorizationCode.objects.select_related('user').get(
                code=code_value, client=client, used=False,
            )
        except OAuthAuthorizationCode.DoesNotExist:
            return JsonResponse({"error": "invalid_grant"}, status=400)

        if auth_code.expires_at < timezone.now():
            return JsonResponse(
                {"error": "invalid_grant", "error_description": "Authorization code has expired"},
                status=400,
            )

        if auth_code.redirect_uri != redirect_uri:
            return JsonResponse(
                {"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
                status=400,
            )

        # PKCE verification (S256)
        if auth_code.code_challenge:
            if not code_verifier:
                return JsonResponse(
                    {"error": "invalid_grant", "error_description": "code_verifier required"},
                    status=400,
                )
            digest = (
                base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
                .rstrip(b'=')
                .decode()
            )
            if digest != auth_code.code_challenge:
                return JsonResponse(
                    {"error": "invalid_grant", "error_description": "PKCE verification failed"},
                    status=400,
                )

        # Consume the code
        auth_code.used = True
        auth_code.save(update_fields=['used'])

        # Issue a long-lived API token (reuses existing APIToken machinery)
        from apps.accounts.models import APIToken
        label = client.client_name or client_id[:12]
        _, raw_token = APIToken.generate(
            user=auth_code.user,
            name=f"MCP OAuth — {label}",
        )
        logger.info(f"[MCP OAuth] Issued API token for {auth_code.user.email} → {label}")

        return JsonResponse({
            "access_token": raw_token,
            "token_type": "bearer",
        })
