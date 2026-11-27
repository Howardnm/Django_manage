import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_mold_injection.models import InjectionTask, MoldType
from app_user.models import Subsidiary


class InjectionTaskFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """注塑任务筛选器 — 状态筛选由列表卡片头部 tab 承载，不在此处作为下拉。"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

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
            ('production_order__code', 'production_order__code'),
        ),
        widget=forms.HiddenInput,
    )

    class Meta:
        model = InjectionTask
        fields = ['q', 'production_base', 'start_date', 'end_date']

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


class MoldTypeFilter(TablerFilterMixin, django_filters.FilterSet):
    """模具台账筛选器。"""

    q = django_filters.CharFilter(method='filter_search', label='搜索')

    mold_type = django_filters.ChoiceFilter(
        choices=MoldType.MoldTypeChoices.choices,
        label='模具类型',
        empty_label='模具类型',
        widget=forms.Select(attrs={'placeholder': '模具类型'}),
    )

    standard = django_filters.ChoiceFilter(
        choices=MoldType.Standard.choices,
        label='测试标准',
        empty_label='测试标准',
        widget=forms.Select(attrs={'placeholder': '测试标准'}),
    )

    status = django_filters.ChoiceFilter(
        choices=MoldType.Status.choices,
        label='状态',
        empty_label='状态',
        widget=forms.Select(attrs={'placeholder': '状态'}),
    )

    class Meta:
        model = MoldType
        fields = ['q', 'mold_type', 'standard', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs['placeholder'] = '检索模具编号 / 模具名称'

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(mold_code__icontains=value) |
            Q(name__icontains=value)
        )
