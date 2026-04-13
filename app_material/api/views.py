import logging
from rest_framework import viewsets, permissions, filters # 导入 DRF 原生 filters
from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from ..models.material import MaterialType, ApplicationScenario, MetricCategory, TestConfig, MaterialLibrary, MaterialDataPoint, MaterialFile
from .serializers import (MaterialTypeSerializer, ApplicationScenarioSerializer, MetricCategorySerializer,
                         TestConfigSerializer, MaterialLibrarySerializer, MaterialDataPointSerializer, MaterialFileSerializer)
from .filters import MaterialLibraryFilter

logger = logging.getLogger(__name__)

class InternalApiTokenPermission(permissions.BasePermission):
    message = 'Invalid or missing Internal API Token.'

    def has_permission(self, request, view):
        if request.method == 'OPTIONS':
            return True
        token = request.headers.get('X-Internal-Api-Token')
        return token == settings.INTERNAL_API_TOKEN

class MaterialTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialType.objects.all()
    serializer_class = MaterialTypeSerializer
    permission_classes = [InternalApiTokenPermission]

class ApplicationScenarioViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApplicationScenario.objects.all()
    serializer_class = ApplicationScenarioSerializer
    permission_classes = [InternalApiTokenPermission]

class MetricCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MetricCategory.objects.all()
    serializer_class = MetricCategorySerializer
    permission_classes = [InternalApiTokenPermission]

class TestConfigViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestConfig.objects.all().select_related('category')
    serializer_class = TestConfigSerializer
    permission_classes = [InternalApiTokenPermission]

class MaterialLibraryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    材料库核心 API：支持多维度过滤 + 全局模糊搜索
    """
    queryset = MaterialLibrary.objects.all().select_related(
        'category'
    ).prefetch_related(
        'scenarios', 
        'characteristics', # 补充特征预加载
        'additional_files', 
        'properties', 
        'properties__test_config', 
        'properties__test_config__category'
    )
    serializer_class = MaterialLibrarySerializer
    permission_classes = [InternalApiTokenPermission]
    
    # 启用过滤器和搜索后端
    filter_backends = [DjangoFilterBackend, filters.SearchFilter] 
    filterset_class = MaterialLibraryFilter
    
    # 定义搜索字段：支持对牌号名和厂家的模糊匹配
    search_fields = ['grade_name', 'manufacturer']

class MaterialDataPointViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialDataPoint.objects.all().select_related('material', 'test_config', 'test_config__category')
    serializer_class = MaterialDataPointSerializer
    permission_classes = [InternalApiTokenPermission]

class MaterialFileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialFile.objects.all().select_related('material')
    serializer_class = MaterialFileSerializer
    permission_classes = [InternalApiTokenPermission]
