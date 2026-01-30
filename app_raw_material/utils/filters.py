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

    # 【新增】性能范围筛选
    # 1. 熔融指数 (Melt Index)
    melt_min = django_filters.NumberFilter(
        method='filter_property_range', 
        label='熔融指数 Min',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min'})
    )
    melt_max = django_filters.NumberFilter(
        method='filter_property_range', 
        label='熔融指数 Max',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max'})
    )

    # 2. 拉伸强度 (Tensile Strength)
    tensile_min = django_filters.NumberFilter(
        method='filter_property_range', 
        label='拉伸强度 Min',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min'})
    )
    tensile_max = django_filters.NumberFilter(
        method='filter_property_range', 
        label='拉伸强度 Max',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max'})
    )

    # 3. 弯曲模量 (Flexural Modulus)
    flex_modulus_min = django_filters.NumberFilter(
        method='filter_property_range', 
        label='弯曲模量 Min',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min'})
    )
    flex_modulus_max = django_filters.NumberFilter(
        method='filter_property_range', 
        label='弯曲模量 Max',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max'})
    )

    # 4. 冲击强度 (Impact Strength)
    impact_min = django_filters.NumberFilter(
        method='filter_property_range', 
        label='冲击强度 Min',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min'})
    )
    impact_max = django_filters.NumberFilter(
        method='filter_property_range', 
        label='冲击强度 Max',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Max'})
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

    # 【核心逻辑】性能范围筛选
    def filter_property_range(self, queryset, name, value):
        if value is None:
            return queryset

        # 1. 解析参数名 (例如: melt_min -> keyword='熔融', op='gte')
        keyword_map = {
            'melt': '熔融',
            'tensile': '拉伸',
            'flex_modulus': '弯曲模量',
            'impact': '冲击',
        }
        
        # 提取前缀 (melt, tensile...) 和后缀 (min, max)
        prefix = '_'.join(name.split('_')[:-1])
        suffix = name.split('_')[-1]
        
        keyword = keyword_map.get(prefix)
        if not keyword:
            return queryset

        # 2. 获取当前标准 (从 request 中获取，如果 View 传递了 request)
        # 注意：django-filter 的 FilterSet 默认不包含 request，需要在 View 初始化时传入
        # self.request 是我们在 View 中手动注入的
        std = getattr(self, 'request', None) and self.request.GET.get('std', 'ISO') or 'ISO'

        # 3. 构建子查询
        # 查找符合条件的 RawMaterialProperty
        # 逻辑：RawMaterial.properties.filter(test_config__name__contains=keyword, value__gte/lte=value)
        
        lookup_expr = 'gte' if suffix == 'min' else 'lte'
        
        # 使用 filter 而不是 exclude，因为我们要保留符合条件的
        # 这里利用 Django 的跨关联查询
        # 注意：这里可能会有性能问题，如果数据量很大，建议使用 annotate + filter
        
        filter_kwargs = {
            'properties__test_config__name__icontains': keyword,
            'properties__test_config__standard__icontains': std,
            f'properties__value__{lookup_expr}': value
        }
        
        return queryset.filter(**filter_kwargs).distinct()

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
