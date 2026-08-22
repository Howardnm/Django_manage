import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_material_testing.models import TestingTask


class TestingTaskFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """测试任务筛选器 — 状态筛选由列表卡片头部 tab 承载，不在此处作为下拉。"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('status', 'status'),
            ('production_order__code', 'production_order__code'),
        ),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = TestingTask
        fields = ['q', 'start_date', 'end_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索工单号 / 实验单号'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(production_order__code__icontains=value) |
            Q(production_order__trial_code__icontains=value) |
            Q(production_order__project__name__icontains=value)
        )
