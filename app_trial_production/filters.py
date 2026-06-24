import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_project.models import Project
from .models import ProductionOrder, ExtrusionTask, SampleInventory


class ProductionOrderFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """生产工单筛选器 — 用于排产总览"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    status = django_filters.ChoiceFilter(
        choices=ProductionOrder.Status.choices,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '工单状态',
            'style': 'width: 150px;',
        }),
    )

    project = django_filters.ModelChoiceFilter(
        queryset=Project.objects.all(),
        widget=forms.Select(attrs={
            'class': 'form-select remote-search',
            'data-model': 'project',
            'placeholder': '检索项目名称',
            'style': 'width: 220px;',
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
        fields = ['q', 'status', 'project', 'start_date', 'end_date']

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

    project = django_filters.ModelChoiceFilter(
        queryset=Project.objects.filter(
            pk__in=ProductionOrder.objects.filter(
                status='ACCEPTED', extrusion_scheduled_date__isnull=True,
            ).values_list('project_id', flat=True).distinct(),
        ),
        widget=forms.Select(attrs={
            'class': 'form-select remote-search',
            'data-model': 'project_pending',
            'placeholder': '检索项目名称',
            'style': 'width: 220px;',
        }),
    )

    class Meta:
        model = ProductionOrder
        fields = ['q', 'project']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索工单号 / 实验单号 / 项目名称'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(code__icontains=value) |
            Q(trial_code__icontains=value) |
            Q(project__name__icontains=value)
        )


class ExtrusionTaskFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """挤出任务筛选器"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    status = django_filters.ChoiceFilter(
        choices=ExtrusionTask.Status.choices,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '任务状态',
            'style': 'width: 150px;',
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
        fields = ['q', 'status', 'start_date', 'end_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索工单号 / 实验单号'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(production_order__code__icontains=value) |
            Q(production_order__trial_code__icontains=value)
        )


class SampleInventoryFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """样品库存筛选器"""
    type = django_filters.ChoiceFilter(choices=SampleInventory.Type.choices)
    sub_type = django_filters.ChoiceFilter(choices=SampleInventory.SubType.choices)
    status = django_filters.ChoiceFilter(choices=SampleInventory.Status.choices)
    trial_code = django_filters.CharFilter(
        field_name='trial_code', lookup_expr='icontains')

    class Meta:
        model = SampleInventory
        fields = ['type', 'sub_type', 'status', 'trial_code']
