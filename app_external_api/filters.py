from django_filters import rest_framework as filters

from app_material.models.material import MaterialLibrary


class MaterialLibraryFilter(filters.FilterSet):
    """材料只读接口过滤器：支持场景/类型/特征的精确筛选。"""
    scenarios = filters.NumberFilter(field_name='scenarios', lookup_expr='id')
    category = filters.NumberFilter(field_name='category', lookup_expr='id')
    characteristics = filters.BaseInFilter(field_name='characteristics__id', lookup_expr='in')

    class Meta:
        model = MaterialLibrary
        fields = ['scenarios', 'category', 'characteristics', 'grade_name', 'manufacturer']
