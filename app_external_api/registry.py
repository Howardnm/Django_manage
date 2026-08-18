"""声明式只读资源注册表。

每个对外暴露的资源用一个 ExposedResource 声明，据此自动生成
ReadOnlyModelViewSet 与路由，避免为每个资源重复手写 ViewSet 样板。
新增资源只需在 RESOURCES 中追加一行。

列表/详情响应级缓存：list()/retrieve() 的序列化结果按
(basename, 规范化 query 串, 会员标记) 分片存入 MaterialCache
（L1 各 Worker 内存 + L2 DatabaseCache 版本号），材料库变动由
app_material.signals 触发失效。
"""
from dataclasses import dataclass
from typing import Callable, Optional

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.response import Response

from app_material.models.material import (
    MaterialType, ApplicationScenario, MaterialCharacteristic, MaterialLibrary,
)
from app_material.services.material_cache import MaterialCache

from .filters import MaterialLibraryFilter
from .permissions import InternalApiTokenPermission, get_member_from_request
from .serializers import (
    MaterialTypeSerializer, ApplicationScenarioSerializer, MaterialCharacteristicSerializer,
    MaterialLightSerializer, MaterialDetailSerializer,
)


@dataclass(frozen=True)
class ExposedResource:
    """一个对外暴露的只读资源声明。"""
    basename: str
    queryset: Callable
    serializer_class: type
    detail_serializer_class: Optional[type] = None
    detail_queryset: Optional[Callable] = None
    filter_backends: tuple = (DjangoFilterBackend, filters.SearchFilter)
    filterset_class: Optional[type] = None
    search_fields: tuple = ()


def _published_materials_list():
    """列表查询集：仅列表渲染所需字段，不 prefetch 物性子表（避免冗余查询）。"""
    return (
        MaterialLibrary.objects.filter(is_published=True)
        .select_related('category')
        .prefetch_related('scenarios', 'characteristics')
    )


def _published_materials_detail():
    """详情查询集：额外 prefetch 物性子表，供 grouped_properties 使用。"""
    return (
        MaterialLibrary.objects.filter(is_published=True)
        .select_related('category')
        .prefetch_related(
            'scenarios', 'characteristics',
            'properties', 'properties__test_config', 'properties__test_config__category',
        )
    )


RESOURCES = (
    ExposedResource(
        basename='types',
        queryset=MaterialType.objects.all,
        serializer_class=MaterialTypeSerializer,
        filter_backends=(),
    ),
    ExposedResource(
        basename='scenarios',
        queryset=ApplicationScenario.objects.all,
        serializer_class=ApplicationScenarioSerializer,
        filter_backends=(),
    ),
    ExposedResource(
        basename='characteristics',
        queryset=MaterialCharacteristic.objects.all,
        serializer_class=MaterialCharacteristicSerializer,
        filter_backends=(),
    ),
    ExposedResource(
        basename='materials',
        queryset=_published_materials_list,
        detail_queryset=_published_materials_detail,
        serializer_class=MaterialLightSerializer,
        detail_serializer_class=MaterialDetailSerializer,
        filterset_class=MaterialLibraryFilter,
        search_fields=('grade_name', 'manufacturer'),
    ),
)


def _query_cache_key(request):
    """规范化 query 参数为稳定的缓存键片段（键值排序 + 多值展开，分页页码亦计入）。"""
    parts = []
    for k in sorted(request.query_params.keys()):
        for v in sorted(request.query_params.getlist(k)):
            parts.append(f"{k}={v}")
    return '&'.join(parts)


def build_viewset(resource):
    """由 ExposedResource 声明生成一个只读 ViewSet 类（含响应级缓存）。"""

    def get_queryset(self, _resource=resource):
        if self.action == 'retrieve' and _resource.detail_queryset:
            return _resource.detail_queryset()
        return _resource.queryset()

    def get_serializer_class(self):
        if self.action == 'retrieve' and resource.detail_serializer_class:
            return resource.detail_serializer_class
        return resource.serializer_class

    def get_serializer_context(self):
        context = viewsets.ReadOnlyModelViewSet.get_serializer_context(self)
        context['is_member'] = get_member_from_request(self.request) is not None
        return context

    def _list(self, request, *args, **kwargs):
        cache_key = f"list:{resource.basename}:{_query_cache_key(request)}"
        data = MaterialCache.get(
            cache_key,
            lambda: viewsets.ReadOnlyModelViewSet.list(self, request, *args, **kwargs).data,
        )
        return Response(data)

    def _retrieve(self, request, *args, **kwargs):
        shard = 'member' if get_member_from_request(request) is not None else 'anon'
        cache_key = f"detail:{resource.basename}:{kwargs.get('pk')}:{shard}"
        data = MaterialCache.get(
            cache_key,
            lambda: viewsets.ReadOnlyModelViewSet.retrieve(self, request, *args, **kwargs).data,
        )
        return Response(data)

    return type(
        f"{resource.basename.title()}ViewSet",
        (viewsets.ReadOnlyModelViewSet,),
        {
            'get_queryset': get_queryset,
            'get_serializer_class': get_serializer_class,
            'get_serializer_context': get_serializer_context,
            'list': _list,
            'retrieve': _retrieve,
            'serializer_class': resource.serializer_class,
            'permission_classes': [InternalApiTokenPermission],
            'filter_backends': list(resource.filter_backends),
            'filterset_class': resource.filterset_class,
            'search_fields': list(resource.search_fields),
            '__doc__': f"只读资源：{resource.basename}",
        },
    )


def register_urls(router):
    """将全部声明资源注册到 DRF router。"""
    for resource in RESOURCES:
        router.register(resource.basename, build_viewset(resource), basename=resource.basename)
