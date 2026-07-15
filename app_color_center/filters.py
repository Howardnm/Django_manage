import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin
from app_trial_production.models import ProductionOrder


class ColorMatchingListFilter(TablerFilterMixin, django_filters.FilterSet):
    """配色任务列表筛选器 — 基于 ProductionOrder（配色任务通过 OneToOne 绑定工单）"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    class Meta:
        model = ProductionOrder
        fields = ['q']

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
