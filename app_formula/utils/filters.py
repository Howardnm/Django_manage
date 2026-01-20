import django_filters
from django import forms
from django.db.models import Q, Subquery, OuterRef, DecimalField
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_formula.models import LabFormula, FormulaTestResult
from app_repository.models import MaterialType

class LabFormulaFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    
    material_type = django_filters.ModelChoiceFilter(
        queryset=MaterialType.objects.all(),
        label='基材类型',
        empty_label="所有类型",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # --- 性能指标范围筛选 ---
    # 密度
    density_min = django_filters.NumberFilter(method='filter_metric', label='密度 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    density_max = django_filters.NumberFilter(method='filter_metric', label='密度 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))
    
    # 熔指
    melt_min = django_filters.NumberFilter(method='filter_metric', label='熔指 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    melt_max = django_filters.NumberFilter(method='filter_metric', label='熔指 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))
    
    # 拉伸强度
    tensile_min = django_filters.NumberFilter(method='filter_metric', label='拉伸 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    tensile_max = django_filters.NumberFilter(method='filter_metric', label='拉伸 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))
    
    # 冲击
    impact_min = django_filters.NumberFilter(method='filter_metric', label='冲击 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    impact_max = django_filters.NumberFilter(method='filter_metric', label='冲击 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))

    # 排序字段
    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('cost_predicted', 'cost_predicted'),
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
        model = LabFormula
        fields = ['q', 'material_type', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(code__icontains=value) |
            Q(name__icontains=value) |
            Q(creator__username__icontains=value)
        )

    def filter_metric(self, queryset, name, value):
        """
        通用指标筛选逻辑
        为了保证筛选结果与列表展示一致，必须使用与 View 中相同的 Subquery 逻辑
        """
        if value is None:
            return queryset

        # 解析指标名称和操作符
        parts = name.split('_')
        operator = parts[-1] # min 或 max
        metric_key = '_'.join(parts[:-1]) # density, melt, tensile...

        # 映射到数据库中的关键词
        keyword_map = {
            'density': '密度',
            'melt': '熔融',
            'tensile': '拉伸强度',
            'impact': '冲击',
        }
        keyword = keyword_map.get(metric_key)
        if not keyword:
            return queryset

        # 获取当前标准
        std = self.request.GET.get('std', 'ISO')

        # 【核心修复】使用 Subquery 进行筛选，确保与列表展示的数据源一致
        # 这里的逻辑必须与 LabFormulaListView.get_queryset 中的 annotate 逻辑保持一致
        # 即：取符合条件的第一条记录
        
        # 1. 构建子查询
        subquery = Subquery(
            FormulaTestResult.objects.filter(
                formula=OuterRef('pk'),
                test_config__name__icontains=keyword,
                test_config__standard__icontains=std
            ).values('value')[:1], # 关键：只取第一条
            output_field=DecimalField()
        )
        
        # 2. 动态 annotate 一个临时字段用于筛选
        # 注意：为了避免与 View 中的 annotate 冲突（虽然通常不会），我们使用一个唯一的临时字段名
        temp_field = f"_filter_{name}"
        
        queryset = queryset.annotate(**{temp_field: subquery})
        
        # 3. 对临时字段进行筛选
        lookup = 'gte' if operator == 'min' else 'lte'
        filter_kwargs = {f"{temp_field}__{lookup}": value}
        
        return queryset.filter(**filter_kwargs)
