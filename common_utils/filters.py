import django_filters
from django import forms


class TablerFormMixin:
    """
    混入类：
    1. 自动给普通字段添加 form-control
    2. 自动给 Checkbox 添加 form-check-input
    3. 自动给 Select 添加 form-select 和 form-select-search (启用 Tom Select)
    4. 自动给 DateInput 添加 form-control 和 type='date'
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # 获取该字段原本可能已经在 widgets 里定义的 class，避免覆盖
            attrs = field.widget.attrs
            existing_class = attrs.get('class', '')
            # -----------------------------------------------------------
            # 情况 1: 下拉选择框 (Select / SelectMultiple)
            # -----------------------------------------------------------
            if isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                # Tabler 标准样式是 form-select，而不是 form-control
                if 'form-select' not in existing_class:
                    existing_class += ' form-select'
                
                # 【修复】只有当字段没有明确指定 Tom Select 行为时，才添加 form-select-search
                # 这些明确指定的行为包括：no-tomselect, value-select, remote-search, tomselect-multi-local
                if (
                    'no-tomselect' not in existing_class and
                    'value-select' not in existing_class and
                    'remote-search' not in existing_class and
                    'tomselect-multi-local' not in existing_class and
                    'form-select-search' not in existing_class # 避免重复添加
                ):
                    existing_class += ' form-select-search'
                    
                attrs['class'] = existing_class.strip()
            # -----------------------------------------------------------
            # 情况 2: 复选框 (Checkbox)
            # -----------------------------------------------------------
            elif isinstance(field.widget, forms.CheckboxInput):
                if 'form-check-input' not in existing_class:
                    attrs['class'] = f"{existing_class} form-check-input".strip()
            # -----------------------------------------------------------
            # 情况 3: 日期输入框 (DateInput)
            # -----------------------------------------------------------
            elif isinstance(field.widget, forms.DateInput):
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()
                attrs['type'] = 'date' # 强制日期控件
            # -----------------------------------------------------------
            # 情况 4: 其他输入框 (Text, Number, Email, File, Password...)
            # -----------------------------------------------------------
            else:
                # 排除 HiddenInput，不需要样式
                if not isinstance(field.widget, forms.HiddenInput):
                    if 'form-control' not in existing_class:
                        attrs['class'] = f"{existing_class} form-control".strip()


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
