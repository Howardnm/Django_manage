from django_filters import rest_framework as filters

from app_material.models.material import MaterialLibrary


class MaterialLibraryFilter(filters.FilterSet):
    """已发布材料列表：场景、类型精确匹配，特征支持逗号分隔的多个 id。"""

    scenarios = filters.NumberFilter(field_name='scenarios', lookup_expr='id')
    category = filters.NumberFilter(field_name='category', lookup_expr='id')
    characteristics = filters.BaseInFilter(field_name='characteristics__id', lookup_expr='in')

    class Meta:
        model = MaterialLibrary
        fields = ['scenarios', 'category', 'characteristics', 'grade_name', 'manufacturer']
