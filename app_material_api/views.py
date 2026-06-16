import logging
from rest_framework import viewsets, permissions, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType

from app_material.models.material import (MaterialType, ApplicationScenario, MetricCategory,
                                          TestConfig, MaterialLibrary, MaterialDataPoint)
from app_repository.models import ExternalMemberActivity, OEM, Customer
from app_user.models import User as CustomUser
from app_attachment.models import Attachment

from .serializers import (MaterialTypeSerializer, ApplicationScenarioSerializer, MetricCategorySerializer,
                         TestConfigSerializer, MaterialLibrarySerializer, MaterialDataPointSerializer,
                         AttachmentFileSerializer)
from .filters import MaterialLibraryFilter

logger = logging.getLogger(__name__)

class InternalApiTokenPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method == 'OPTIONS': return True
        token = request.headers.get('X-Internal-Api-Token')
        return token == settings.INTERNAL_API_TOKEN

# ==========================================
# 1. 外部会员鉴权引擎 (适配 4D 架构)
# ==========================================
class MemberAuthVerifyView(APIView):
    """
    提供给子系统的会员验证接口。
    返回精简的 4D 身份画像，仅包含鉴权和角色判断所需信息。
    """
    permission_classes = [InternalApiTokenPermission]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response({'status': 'error', 'message': '请输入用户名和密码'}, status=400)

        user = authenticate(request=request, username=username, password=password)

        if user is not None:
            if not user.is_active:
                return Response({'status': 'error', 'message': '该账号已被禁用'}, status=403)

            # --- 构建精简的 4D 身份画像数据包 ---
            profile_data = {
                'display_name': user.get_full_name() or user.username,
                'user_type': user.user_type,
                'user_level': user.user_level,
                'dept_code': user.department.code if user.department else "NONE",
            }

            # --- 确定唯一令牌 (Token) ---
            token = str(user.member_token)

            # --- 确定角色和显示名称 ---
            role = 'GUEST'
            if user.is_staff:
                role = 'STAFF'
            elif user.associated_oem:
                role = 'OEM'
                profile_data['display_name'] = user.associated_oem.name
            elif user.associated_customer:
                role = 'CUSTOMER'
                profile_data['display_name'] = user.associated_customer.company_name

            if not token:
                return Response({'status': 'error', 'message': '账号未生成唯一令牌，请联系管理员'}, status=500)

            profile_data['role'] = role
            profile_data['token'] = token

            return Response({
                'status': 'success',
                'user': profile_data
            })

        return Response({'status': 'error', 'message': '用户名或密码错误'}, status=401)

# ==========================================
# 2. 行为日志回流
# ==========================================
class MemberActivityFeedbackView(APIView):
    permission_classes = [InternalApiTokenPermission]
    def post(self, request):
        logs = request.data.get('logs', [])
        created_count = 0
        for item in logs:
            if item.get('member_token'):
                ExternalMemberActivity.objects.create(
                    member_token=item['member_token'],
                    action=item['action'],
                    target_name=item['target_name'],
                    timestamp=item['timestamp']
                )
                created_count += 1
        return Response({'status': 'success', 'received': created_count})

# ==========================================
# 3. 受限下载流接口（从 Attachment 表查询）
# ==========================================
class MaterialInternalDownloadView(APIView):
    permission_classes = [InternalApiTokenPermission]

    def get(self, request, pk, file_type):
        material = get_object_or_404(MaterialLibrary, pk=pk)
        category = file_type.upper()

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

# ==========================================
# 4. 只读资源接口 (供同步抓取)
# ==========================================
class MaterialTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialType.objects.all(); serializer_class = MaterialTypeSerializer; permission_classes = [InternalApiTokenPermission]
class ApplicationScenarioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApplicationScenario.objects.all(); serializer_class = ApplicationScenarioSerializer; permission_classes = [InternalApiTokenPermission]
class MetricCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MetricCategory.objects.all(); serializer_class = MetricCategorySerializer; permission_classes = [InternalApiTokenPermission]
class TestConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestConfig.objects.all().select_related('category'); serializer_class = TestConfigSerializer; permission_classes = [InternalApiTokenPermission]
class MaterialLibraryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialLibrary.objects.all().select_related('category').prefetch_related('scenarios', 'characteristics', 'properties', 'properties__test_config', 'properties__test_config__category')
    serializer_class = MaterialLibrarySerializer; permission_classes = [InternalApiTokenPermission]; filter_backends = [DjangoFilterBackend, filters.SearchFilter]; filterset_class = MaterialLibraryFilter; search_fields = ['grade_name', 'manufacturer']
class MaterialDataPointViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialDataPoint.objects.all().select_related('material', 'test_config', 'test_config__category'); serializer_class = MaterialDataPointSerializer; permission_classes = [InternalApiTokenPermission]
class AttachmentFileViewSet(viewsets.ReadOnlyModelViewSet):
    """附件视图集 — 从 Attachment 表查询 MaterialLibrary 的附件"""
    serializer_class = AttachmentFileSerializer
    permission_classes = [InternalApiTokenPermission]

    def get_queryset(self):
        ct = ContentType.objects.get_for_model(MaterialLibrary)
        return Attachment.objects.filter(
            content_type=ct, is_deleted=False,
        ).select_related('uploader').order_by('-uploaded_at')
