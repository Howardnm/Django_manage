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
    混入类：自动给 FilterSet 中的字段添加 Tabler/Bootstrap 样式类 + TomSelect 适配

    Select/SelectMultiple 自动添加 form-select + form-select-search（启用本地搜索），
    但排除以下类：no-tomselect, value-select, remote-search, tomselect-multi-local
    """

    # 排除类集合 — 这些类有专属的 TomSelect 初始化方式
    _TS_EXCLUDE_CLASSES = {'no-tomselect', 'value-select', 'remote-search', 'tomselect-multi-local'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.filters.items():
            widget = field.field.widget
            attrs = widget.attrs
            existing_class = attrs.get('class', '')

            if field_name == 'q':
                attrs.update({
                    'class': 'form-control',
                    'placeholder': attrs.get('placeholder', '输入关键字搜索...')
                })

            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                # 确保 form-select 存在
                if 'form-select' not in existing_class:
                    attrs['class'] = f"{existing_class} form-select".strip()
                    existing_class = attrs['class']

                # 自动添加 form-select-search（本地搜索），除非被排除
                if not self._TS_EXCLUDE_CLASSES & set(existing_class.split()):
                    if 'form-select-search' not in existing_class:
                        attrs['class'] = f"{existing_class} form-select-search".strip()

            elif isinstance(widget, forms.DateInput):
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()
                attrs['type'] = 'date'

            elif isinstance(widget, forms.TextInput):
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()


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
