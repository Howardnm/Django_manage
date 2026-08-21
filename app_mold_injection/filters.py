import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_mold_injection.models import InjectionTask


class InjectionTaskFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """注塑任务筛选器 — 状态筛选由列表卡片头部 tab 承载，不在此处作为下拉。"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    source = django_filters.ChoiceFilter(
        choices=InjectionTask.Source.choices,
        widget=forms.Select(attrs={
            'class': 'form-select form-select-search',
            'placeholder': '来源渠道',
            'style': 'width: 150px;',
        }),
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('status', 'status'),
            ('production_order__code', 'production_order__code'),
        ),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = InjectionTask
        fields = ['q', 'source', 'start_date', 'end_date']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索关联工单号 / 实验单号'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(production_order__code__icontains=value) |
            Q(production_order__trial_code__icontains=value) |
            Q(production_order__project__name__icontains=value)
        )
