import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_project.models import Project
from app_user.models import Subsidiary
from .models import ProductionOrder, ExtrusionTask


class ProductionOrderFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """生产工单筛选器 — 用于排产总览"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    status = django_filters.ChoiceFilter(
        choices=ProductionOrder.Status.choices,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '工单状态',
        }),
    )

    project = django_filters.ModelChoiceFilter(
        queryset=Project.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-select remote-search',
            'data-model': 'project',
            'placeholder': '检索项目名称',
        }),
    )

    production_base = django_filters.ModelChoiceFilter(
        queryset=Subsidiary.objects.order_by('name'),
        label='生产基地',
        empty_label='生产基地',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '生产基地',
        }),
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('code', 'code'),
            ('quantity_planned', 'quantity_planned'),
        ),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = ProductionOrder
        fields = ['q', 'status', 'project', 'production_base', 'start_date', 'end_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 覆盖 TablerFilterMixin 的默认 placeholder，说明检索字段
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索工单号 / 实验单号 / 项目名称'

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(code__icontains=value) |
            Q(trial_code__icontains=value) |
            Q(project__name__icontains=value)
        )


class PendingOrderFilter(TablerFilterMixin, django_filters.FilterSet):
    """待排产工单筛选器 — 排产工作台待排产卡片专用（HTMX 渲染）"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    project = django_filters.CharFilter(
        field_name='project__name',
        lookup_expr='icontains',
        label='项目名称',
        widget=forms.TextInput(attrs={
            'placeholder': '检索项目名称',
            'class': 'form-control js-filter-keyword',
        }),
    )

    production_base = django_filters.ModelChoiceFilter(
        queryset=Subsidiary.objects.order_by('name'),
        label='生产基地',
        empty_label='生产基地',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '生产基地',
        }),
    )

    class Meta:
        model = ProductionOrder
        fields = ['q', 'project', 'production_base']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索工单号 / 实验单号'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(code__icontains=value) |
            Q(trial_code__icontains=value)
        )


class ExtrusionTaskFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """挤出任务筛选器"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    project = django_filters.CharFilter(
        field_name='production_order__project__name',
        lookup_expr='icontains',
        label='项目名称',
        widget=forms.TextInput(attrs={
            'placeholder': '检索项目名称',
            'class': 'form-control js-filter-keyword',
        }),
    )

    status = django_filters.ChoiceFilter(
        choices=ExtrusionTask.Status.choices,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '任务状态',
        }),
    )

    production_base = django_filters.ModelChoiceFilter(
        field_name='production_order__production_base',
        queryset=Subsidiary.objects.order_by('name'),
        label='生产基地',
        empty_label='生产基地',
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '生产基地',
        }),
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('status', 'status'),
        ),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = ExtrusionTask
        fields = ['q', 'project', 'status', 'production_base', 'start_date', 'end_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 日期来自 Mixin，声明顺序排在前面。筛选项按：搜索、项目名称、其余。
        order = ['q', 'project', 'status', 'production_base', 'start_date', 'end_date', 'sort']
        self.filters = {name: self.filters[name] for name in order if name in self.filters}
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索工单号 / 实验单号'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(production_order__code__icontains=value) |
            Q(production_order__trial_code__icontains=value)
        )


