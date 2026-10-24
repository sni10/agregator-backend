import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasPublishingKey(BasePermission):
    """`X-Api-Key` equals PUBLISHING_API_KEY. No key configured -> everyone is refused."""

    message = 'Missing or invalid X-Api-Key.'

    def has_permission(self, request, view):
        key = settings.PUBLISHING_API_KEY
        given = request.headers.get('X-Api-Key', '')
        return bool(key) and hmac.compare_digest(given.encode(), key.encode())
