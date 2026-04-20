import logging
from rest_framework import viewsets, permissions, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse
from django.shortcuts import get_object_or_404

from app_material.models.material import (MaterialType, ApplicationScenario, MetricCategory, 
                                          TestConfig, MaterialLibrary, MaterialDataPoint, MaterialFile)
from app_repository.models import ExternalMemberActivity, OEM, Customer # 导入 Customer 和 OEM
from app_user.models import User as CustomUser # 导入自定义 User 模型，避免命名冲突

from .serializers import (MaterialTypeSerializer, ApplicationScenarioSerializer, MetricCategorySerializer,
                         TestConfigSerializer, MaterialLibrarySerializer, MaterialDataPointSerializer, 
                         MaterialFileSerializer)
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
                'display_name': user.get_full_name() or user.username, # 用于前端显示
                'user_type': user.user_type,
                'user_level': user.user_level,
                'dept_code': user.department.code if user.department else "NONE", # 部门编码，非敏感
            }

            # --- 确定唯一令牌 (Token) ---
            token = str(user.member_token) # 直接从 User 模型获取 member_token

            # --- 确定角色和显示名称 ---
            role = 'GUEST' # 默认角色
            if user.is_staff:
                role = 'STAFF'
            elif user.associated_oem:
                role = 'OEM'
                profile_data['display_name'] = user.associated_oem.name # 优先显示主机厂名
            elif user.associated_customer:
                role = 'CUSTOMER'
                profile_data['display_name'] = user.associated_customer.company_name # 优先显示客户公司名
            
            # 确保 token 存在 (User 模型现在自带 member_token)
            if not token: # 理论上不会发生，因为 User 模型有 default=uuid.uuid4
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
# 3. 受限下载流接口
# ==========================================
class MaterialInternalDownloadView(APIView):
    permission_classes = [InternalApiTokenPermission]

    def get(self, request, pk, file_type):
        material = get_object_or_404(MaterialLibrary, pk=pk)
        field_name = f"file_{file_type.lower()}"
        file_field = getattr(material, field_name, None)
        
        if not file_field:
            return Response({'error': 'File not found'}, status=404)

        return FileResponse(file_field.open('rb'), as_attachment=True)

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
    queryset = MaterialLibrary.objects.all().select_related('category').prefetch_related('scenarios', 'characteristics', 'additional_files', 'properties', 'properties__test_config', 'properties__test_config__category')
    serializer_class = MaterialLibrarySerializer; permission_classes = [InternalApiTokenPermission]; filter_backends = [DjangoFilterBackend, filters.SearchFilter]; filterset_class = MaterialLibraryFilter; search_fields = ['grade_name', 'manufacturer']
class MaterialDataPointViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialDataPoint.objects.all().select_related('material', 'test_config', 'test_config__category'); serializer_class = MaterialDataPointSerializer; permission_classes = [InternalApiTokenPermission]
class MaterialFileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialFile.objects.all().select_related('material'); serializer_class = MaterialFileSerializer; permission_classes = [InternalApiTokenPermission]
