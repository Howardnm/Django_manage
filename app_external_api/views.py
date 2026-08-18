import logging

from django.contrib.auth import authenticate
from django.contrib.contenttypes.models import ContentType
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from app_attachment.models import Attachment
from app_material.models.material import MaterialLibrary
from app_material.services.material_cache import MaterialCache

from .models import ExternalMemberActivity
from .permissions import InternalApiTokenPermission, MemberTokenPermission

logger = logging.getLogger(__name__)

# 下载端点路径参数 → Attachment.category 规范值（RoHS 为大小写混合）
DOWNLOAD_CATEGORY_MAP = {'tds': 'TDS', 'msds': 'MSDS', 'rohs': 'RoHS'}


class MemberAuthVerifyView(APIView):
    """会员身份鉴权：返回精简的 4D 身份画像。"""
    permission_classes = [InternalApiTokenPermission]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth_verify'

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({'status': 'error', 'message': '请输入邮箱和密码'}, status=400)

        user = authenticate(request=request, email=email, password=password)
        if user is None:
            return Response({'status': 'error', 'message': '邮箱或密码错误'}, status=401)

        display_name = user.get_full_name() or user.username

        return Response({
            'status': 'success',
            'user': {
                'display_name': display_name,
                'token': str(user.member_token),
                'user_type': user.user_type.code if user.user_type_id else None,
                'user_level': user.user_level,
                'dept_code': user.department.code if user.department_id else 'NONE',
            },
        })


class MemberActivityFeedbackView(APIView):
    """行为日志回流：逐条容错，坏数据跳过而非整批失败。"""
    permission_classes = [InternalApiTokenPermission]

    def post(self, request):
        logs = request.data.get('logs', [])
        received = skipped = 0
        for item in logs:
            raw_ts = item.get('timestamp')
            try:
                ts = parse_datetime(raw_ts) if raw_ts else None
            except (TypeError, ValueError):
                ts = None

            if not item.get('member_token') or not item.get('action') or ts is None:
                skipped += 1
                continue

            ExternalMemberActivity.objects.create(
                member_token=item['member_token'],
                action=item['action'],
                target_name=item.get('target_name', ''),
                timestamp=ts,
            )
            received += 1

        return Response({'status': 'success', 'received': received, 'skipped': skipped})


def _build_nav_tree():
    """构建目录导航树（场景 → 类型 → 特征，携带计数）。"""
    products = (
        MaterialLibrary.objects.filter(is_published=True)
        .select_related('category')
        .prefetch_related('scenarios', 'characteristics')
    )

    tree_map = {}
    for p in products:
        type_id, type_name = p.category_id, p.category.name
        for s in p.scenarios.all():
            node = tree_map.setdefault(s.id, {'name': s.name, 'count': 0, 'types': {}})
            t_node = node['types'].setdefault(
                type_id, {'name': type_name, 'count': 0, 'characteristics': {}}
            )
            node['count'] += 1
            t_node['count'] += 1
            for c in p.characteristics.all():
                c_node = t_node['characteristics'].setdefault(c.id, {'name': c.name, 'count': 0})
                c_node['count'] += 1

    result = []
    for s_id, s_info in tree_map.items():
        sce = {'id': s_id, 'name': s_info['name'], 'count': s_info['count'], 'types': []}
        for t_id, t_info in sorted(s_info['types'].items()):
            sce['types'].append({
                'id': t_id,
                'name': t_info['name'],
                'count': t_info['count'],
                'characteristics': [
                    {'id': c_id, 'name': c_info['name'], 'count': c_info['count']}
                    for c_id, c_info in sorted(t_info['characteristics'].items())
                ],
            })
        result.append(sce)

    return sorted(result, key=lambda x: x['name'])


class CatalogNavTreeView(APIView):
    """目录导航树：场景 → 类型 → 特征，携带计数，供纯前端目录渲染。"""
    permission_classes = [InternalApiTokenPermission]

    def get(self, request):
        return Response(MaterialCache.get('nav_tree', _build_nav_tree))


class CacheVersionView(APIView):
    """对外数据版本号：供电子手册子系统校验本地缓存是否过期。"""
    permission_classes = [InternalApiTokenPermission]

    def get(self, request):
        return Response({'version': MaterialCache.current_version()})


class MaterialInternalDownloadView(APIView):
    """受限文档下载：从 Attachment 表返回文件流（需内部令牌 + 会员令牌）。"""
    permission_classes = [InternalApiTokenPermission, MemberTokenPermission]

    def get(self, request, pk, file_type):
        category = DOWNLOAD_CATEGORY_MAP.get(file_type.lower())
        if category is None:
            raise Http404("不支持的文档类型")

        material = get_object_or_404(MaterialLibrary, pk=pk)
        ct = ContentType.objects.get_for_model(MaterialLibrary)
        att = get_object_or_404(
            Attachment,
            content_type=ct, object_id=material.pk,
            category=category, is_deleted=False,
        )
        try:
            return FileResponse(att.file.open('rb'), as_attachment=True)
        except FileNotFoundError:
            raise Http404("物理文件丢失")
