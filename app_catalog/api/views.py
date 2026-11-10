"""CRM 目录 API。视图只解析参数、调用查询/服务并返回响应。"""
from django.http import FileResponse, Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter
from rest_framework.views import APIView

from app_catalog.api.filters import MaterialLibraryFilter
from app_catalog.api.permissions import CatalogApiKeyAuthentication, CatalogApiKeyPermission
from app_catalog.api.serializers import MaterialDetailSerializer, MaterialLightSerializer
from app_catalog.selectors import published_material_detail, published_materials
from app_catalog.services.catalog import CatalogReadService, query_cache_key


class CatalogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class CatalogAPIView(APIView):
    authentication_classes = [CatalogApiKeyAuthentication]
    permission_classes = [CatalogApiKeyPermission]


class CatalogNavTreeView(CatalogAPIView):
    """场景 → 类型 → 特征，带计数和背景图地址。"""

    def get(self, request):
        return Response(CatalogReadService.nav_tree(request))


class CatalogBackgroundView(CatalogAPIView):
    """场景 / 类型 / 特征的导航背景图。内联流出，不给媒体目录直链。"""

    def get(self, request, kind, pk):
        attachment = CatalogReadService.background_file(kind, pk)
        try:
            return FileResponse(attachment.file.open('rb'), as_attachment=False)
        except FileNotFoundError:
            raise Http404("物理文件丢失")


class MaterialDownloadView(CatalogAPIView):
    """TDS / MSDS / RoHS 文件流。不返回媒体目录直链。"""

    def get(self, request, pk, file_type):
        attachment = CatalogReadService.download_file(pk, file_type)
        try:
            return FileResponse(attachment.file.open('rb'), as_attachment=True)
        except FileNotFoundError:
            raise Http404("物理文件丢失")


class PublishedMaterialViewSet(viewsets.ReadOnlyModelViewSet):
    """已发布材料列表与详情。"""

    authentication_classes = [CatalogApiKeyAuthentication]
    permission_classes = [CatalogApiKeyPermission]
    pagination_class = CatalogPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = MaterialLibraryFilter
    search_fields = ['grade_name', 'manufacturer']

    def get_queryset(self):
        if getattr(self, 'action', None) == 'retrieve':
            return published_material_detail()
        return published_materials()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return MaterialDetailSerializer
        return MaterialLightSerializer

    def list(self, request, *args, **kwargs):
        data = CatalogReadService.cached_list(
            query_cache_key(request.query_params),
            lambda: viewsets.ReadOnlyModelViewSet.list(self, request, *args, **kwargs).data,
        )
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        data = CatalogReadService.cached_detail(
            kwargs.get('pk'),
            lambda: viewsets.ReadOnlyModelViewSet.retrieve(self, request, *args, **kwargs).data,
        )
        return Response(data)


router = SimpleRouter()
router.register('materials', PublishedMaterialViewSet, basename='material')
