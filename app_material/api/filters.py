from django_filters import rest_framework as filters
from ..models.material import MaterialLibrary

class MaterialLibraryFilter(filters.FilterSet):
    """
    全能 API 过滤器：支持场景、分类、特征属性的精确过滤
    """
    # 场景过滤 (?scenarios=ID)
    scenarios = filters.NumberFilter(field_name='scenarios', lookup_expr='id')
    
    # 材质分类过滤 (?category=ID)
    category = filters.NumberFilter(field_name='category', lookup_expr='id')

    # 【新增】特征属性过滤 (?characteristics=ID)
    # 支持多选过滤：如果传入 ?characteristics=1&characteristics=2，将返回具备任一特征的材料
    characteristics = filters.BaseInFilter(field_name='characteristics__id', lookup_expr='in')

    class Meta:
        model = MaterialLibrary
        fields = ['scenarios', 'category', 'characteristics', 'grade_name', 'manufacturer']
