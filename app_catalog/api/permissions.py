"""目录 API 只认服务端密钥，不认浏览器会话。失败返回 401。"""
from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions, permissions
from rest_framework.authentication import BaseAuthentication

from app_user.services.service_api_key import authenticate_service_api_key


def _bearer_token(request):
    header = request.headers.get('Authorization', '')
    prefix = 'Bearer '
    if not header.startswith(prefix):
        return ''
    return header[len(prefix):].strip()


class CatalogApiKeyAuthentication(BaseAuthentication):
    """Authorization: Bearer cat_... 校验。无头返回 None，由权限类转成 401。"""

    def authenticate(self, request):
        token = _bearer_token(request)
        if not token:
            return None
        key = authenticate_service_api_key(token)
        if key is None:
            raise exceptions.AuthenticationFailed('无效的目录 API 密钥')
        return (AnonymousUser(), key)

    def authenticate_header(self, request):
        return 'Bearer'


class CatalogApiKeyPermission(permissions.BasePermission):
    """必须已通过 CatalogApiKeyAuthentication。OPTIONS 放行。"""

    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        return request.successful_authenticator is not None
