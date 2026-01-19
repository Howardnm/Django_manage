import django_filters
from django import forms

class TablerFilterMixin:
    """
    混入类：自动给 FilterSet 中的字段添加 Tabler/Bootstrap 样式类
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 1. 给搜索框 'q' 添加样式
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs.update({
                'class': 'form-control',
                'placeholder': '输入关键字搜索...'
            })

        # 2. 遍历所有字段，根据 Widget 类型添加样式
        # 注意：django-filters 的 form 是动态生成的，有时直接修改 filters 里的 widget attrs 更有效
        pass 
        # (目前的实现主要针对 q，如果需要自动处理所有 Select/Input，可以在这里扩展，
        # 但为了保持兼容性，我们暂时只保留你之前代码中的逻辑，即主要处理 q，
        # 其他字段在定义时通过 widget=forms.Select(attrs={'class': 'form-select'}) 指定)


class DateRangeFilterMixin(django_filters.FilterSet):
    """
    通用日期范围筛选 Mixin (默认针对 created_at)
    """
    start_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        label='开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='lte',
        label='结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )


class DateRangeUpdatedFilterMixin(django_filters.FilterSet):
    """
    通用日期范围筛选 Mixin (针对 updated_at)
    适用于档案、记录等以更新时间为准的模型
    """
    start_date = django_filters.DateFilter(
        field_name='updated_at',
        lookup_expr='gte',
        label='开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = django_filters.DateFilter(
        field_name='updated_at',
        lookup_expr='lte',
        label='结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
