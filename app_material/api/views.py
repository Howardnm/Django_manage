import logging
from rest_framework import viewsets, permissions
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
    queryset = TestConfig.objects.all().select_related('category') # 优化：预加载分类
    serializer_class = TestConfigSerializer
    permission_classes = [InternalApiTokenPermission]

class MaterialLibraryViewSet(viewsets.ReadOnlyModelViewSet):
    # 核心优化：深度预加载所有关联数据，避免 N+1 查询
    queryset = MaterialLibrary.objects.all().select_related(
        'category' # MaterialType
    ).prefetch_related(
        'scenarios', # ApplicationScenario (M2M)
        'additional_files', # MaterialFile (Reverse FK)
        'properties', # MaterialDataPoint (Reverse FK)
        'properties__test_config', # MaterialDataPoint -> TestConfig
        'properties__test_config__category' # MaterialDataPoint -> TestConfig -> MetricCategory
    )
    serializer_class = MaterialLibrarySerializer
    permission_classes = [InternalApiTokenPermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = MaterialLibraryFilter

class MaterialDataPointViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialDataPoint.objects.all().select_related('material', 'test_config', 'test_config__category') # 优化：预加载关联
    serializer_class = MaterialDataPointSerializer
    permission_classes = [InternalApiTokenPermission]

class MaterialFileViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MaterialFile.objects.all().select_related('material') # 优化：预加载材料
    serializer_class = MaterialFileSerializer
    permission_classes = [InternalApiTokenPermission]
