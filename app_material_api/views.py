import logging
from rest_framework import viewsets, permissions, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth import authenticate
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse, Http404

from app_material.models.material import (MaterialType, ApplicationScenario, MetricCategory, 
                                          TestConfig, MaterialLibrary, MaterialDataPoint, MaterialFile)
from app_repository.models import ExternalMemberActivity, OEM, Customer

from .serializers import (MaterialTypeSerializer, ApplicationScenarioSerializer, MetricCategorySerializer,
                         TestConfigSerializer, MaterialLibrarySerializer, MaterialDataPointSerializer, 
                         MaterialFileSerializer, MaterialCharacteristicSerializer)
from .filters import MaterialLibraryFilter

logger = logging.getLogger(__name__)

class InternalApiTokenPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method == 'OPTIONS': return True
        token = request.headers.get('X-Internal-Api-Token')
        return token == settings.INTERNAL_API_TOKEN

# --- 外部会员验证接口 ---
class MemberAuthVerifyView(APIView):
    permission_classes = [InternalApiTokenPermission]
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        if not username or not password: return Response({'status': 'error', 'message': '请输入用户名和密码'}, status=400)
        user = authenticate(request=request, username=username, password=password)
        if user is not None:
            if not user.is_active: return Response({'status': 'error', 'message': '该账号已被禁用'}, status=403)
            role = 'GUEST'; token = None; display_name = user.get_full_name() or user.username
            if user.is_staff: role = 'STAFF'; token = f"staff_{user.id}"
            elif hasattr(user, 'oem_profile'): role = 'OEM'; token = str(user.oem_profile.member_token); display_name = user.oem_profile.name
            elif hasattr(user, 'customer_profile'): role = 'CUSTOMER'; token = str(user.customer_profile.member_token); display_name = user.customer_profile.company_name
            if not token: return Response({'status': 'error', 'message': '账号未关联会员资料'}, status=403)
            return Response({'status': 'success', 'user': {'username': user.username, 'role': role, 'token': token, 'display_name': display_name}})
        return Response({'status': 'error', 'message': '用户名或密码错误'}, status=401)

# --- 行为日志回流接收接口 ---
class MemberActivityFeedbackView(APIView):
    permission_classes = [InternalApiTokenPermission]
    def post(self, request):
        logs = request.data.get('logs', [])
        if not isinstance(logs, list): return Response({'status': 'error', 'message': 'Invalid format'}, status=400)
        created_count = 0
        for item in logs:
            if item.get('member_token'):
                ExternalMemberActivity.objects.create(member_token=item['member_token'], action=item['action'], target_name=item['target_name'], timestamp=item['timestamp'])
                created_count += 1
        return Response({'status': 'success', 'received': created_count})

# --- 文件流输出接口 (专供中转下载) ---
class MaterialInternalDownloadView(APIView):
    """
    提供受限的文件流下载接口。
    """
    permission_classes = [InternalApiTokenPermission]

    def get(self, request, pk, file_type):
        material = get_object_or_404(MaterialLibrary, pk=pk)
        
        # 校验字段是否存在
        field_name = f"file_{file_type.lower()}"
        if not hasattr(material, field_name):
            return Response({'error': 'Invalid file type'}, status=400)
            
        file_field = getattr(material, field_name)
        if not file_field:
            return Response({'error': 'File not found'}, status=404)

        try:
            return FileResponse(file_field.open('rb'), as_attachment=True)
        except FileNotFoundError:
            return Response({'error': 'Physical file missing'}, status=404)

from django.shortcuts import get_object_or_404 # 确保导入了

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
