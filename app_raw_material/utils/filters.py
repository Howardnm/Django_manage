import django_filters
from django import forms
from django.db.models import Q, Subquery, OuterRef, DecimalField
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_raw_material.models import Supplier, RawMaterial, RawMaterialType, RawMaterialProperty
from app_repository.models import MaterialType

# 1. 供应商过滤器
class SupplierFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    class Meta:
        model = Supplier
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(sales_contact__icontains=value) |
            Q(tech_contact__icontains=value)
        )

# 2. 原材料过滤器
class RawMaterialFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    
    category = django_filters.ModelChoiceFilter(
        queryset=RawMaterialType.objects.all(),
        label='类型',
        empty_label="所有类型",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    supplier = django_filters.ModelChoiceFilter(
        queryset=Supplier.objects.all(),
        label='供应商',
        empty_label="所有供应商",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # 【新增】适用体系筛选 (多选)
    suitable_materials = django_filters.ModelMultipleChoiceFilter(
        queryset=MaterialType.objects.all(),
        field_name='suitable_materials', # 多对多筛选
        label='适用体系',
        # 使用 SelectMultiple 控件，并添加 form-select-search 类以启用 Tom Select
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-search'}),
        conjoined=False # False 表示 OR 关系 (只要包含其中一个即可)，True 表示 AND 关系
    )

    # 【新增】排序字段
    sort = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('model_name', 'model_name'),
            ('category__name', 'category'),
            ('cost_price', 'cost_price'),
            ('created_at', 'created_at'),
            # 动态性能指标排序 (需要在 View 中 annotate)
            ('val_density', 'density'),
            ('val_ash', 'ash'),
            ('val_melt', 'melt_index'),
            ('val_tensile', 'tensile'),
            ('val_flex_strength', 'flex_strength'),
            ('val_flex_modulus', 'flex_modulus'),
            ('val_impact', 'impact'),
            ('val_hdt', 'hdt'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = RawMaterial
        # start_date, end_date 来自 DateRangeFilterMixin，默认筛选 created_at
        fields = ['q', 'category', 'supplier', 'suitable_materials', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(model_name__icontains=value) |
            Q(warehouse_code__icontains=value)
        )

# 3. 原材料类型过滤器
class RawMaterialTypeFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('order', 'order'),
            ('name', 'name'),
            ('code', 'code'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = RawMaterialType
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(code__icontains=value) |
            Q(description__icontains=value)
        )
