"""
Custom middleware for CodeVault API.
"""
import time
import logging
from django.core.cache import cache
from django.http import JsonResponse
from django.conf import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Simple rate limiter using Django cache.
    Limits requests per IP address within a configurable window.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.max_requests = getattr(settings, 'RATE_LIMIT_REQUESTS', 100)
        self.window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        ip = self._get_client_ip(request)
        cache_key = f"ratelimit:{ip}"

        try:
            request_count = cache.get(cache_key, 0)
            if request_count >= self.max_requests:
                return JsonResponse(
                    {'error': 'Rate limit exceeded. Try again later.'},
                    status=429,
                )
            cache.set(cache_key, request_count + 1, self.window)
        except Exception as e:
            logger.warning(f"Rate limit cache error: {e}")

        response = self.get_response(request)
        response['X-RateLimit-Limit'] = str(self.max_requests)
        response['X-RateLimit-Remaining'] = str(max(0, self.max_requests - request_count - 1))
        return response

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '0.0.0.0')


class RequestTimingMiddleware:
    """Adds X-Request-Time header to all responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.time()
        response = self.get_response(request)
        duration_ms = int((time.time() - start) * 1000)
        response['X-Request-Time-Ms'] = str(duration_ms)
        return response
