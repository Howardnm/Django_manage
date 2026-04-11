from django_filters import rest_framework as filters
from ..models.material import MaterialLibrary

class MaterialLibraryFilter(filters.FilterSet):
    """
    为 MaterialLibrary 模型定义过滤器，专门针对多对多关联进行优化
    """
    # 针对应用场景场景 ID 的过滤
    # 当传递 ?scenarios=1 时，会执行 MaterialLibrary.objects.filter(scenarios__id=1)
    scenarios = filters.NumberFilter(field_name='scenarios', lookup_expr='id')
    
    # 针对材质分类 ID 的过滤
    category = filters.NumberFilter(field_name='category', lookup_expr='id')

    class Meta:
        model = MaterialLibrary
        fields = ['scenarios', 'category', 'grade_name', 'manufacturer']
