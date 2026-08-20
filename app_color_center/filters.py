import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_trial_production.models import ProductionOrder
from app_project.models import Project


class ColorTaskFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """配色任务列表筛选器 — 按工单维度"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(('created_at', 'created_at'), ('code', 'code')),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = ProductionOrder
        fields = ['q', 'start_date', 'end_date']

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


class ColorProjectFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """配色项目列表筛选器"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    class Meta:
        model = Project
        fields = ['q', 'start_date', 'end_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索项目名称 / 成品材料 / SAP编码'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(material__grade_name__icontains=value) |
            Q(material__sap_material_code__icontains=value)
        )
