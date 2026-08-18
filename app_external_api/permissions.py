import hmac
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import permissions


class InternalApiTokenPermission(permissions.BasePermission):
    """内部 API 令牌鉴权：恒定时间比较，防止时序侧信道攻击。"""

    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        token = request.headers.get('X-Internal-Api-Token', '')
        expected = getattr(settings, 'INTERNAL_API_TOKEN', '')
        return bool(expected) and hmac.compare_digest(token, expected)


def get_member_from_request(request):
    """从请求头 X-Member-Token 解析有效会员，无效或缺失返回 None。"""
    token = request.headers.get('X-Member-Token', '')
    if not token:
        return None
    # member_token 为 UUID 字段，非法值会触发 DB 层 ValidationError → 500，先校验再查询
    try:
        uuid.UUID(token)
    except (ValueError, TypeError, AttributeError):
        return None
    User = get_user_model()
    return User.objects.filter(member_token=token, is_active=True).first()


class MemberTokenPermission(permissions.BasePermission):
    """会员令牌鉴权：要求请求头携带有效会员令牌。"""

    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        return get_member_from_request(request) is not None
