"""产品报价需求单过滤器。"""

import django_filters
from django import forms
from django.db.models import Q

from common_utils.filters import TablerFilterMixin

from .models import QuotationRequest


class QuotationFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search', label='搜索',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '搜需求单号/成品牌号/客户...',
        }),
    )
    status = django_filters.ChoiceFilter(
        choices=QuotationRequest.Status.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = QuotationRequest
        fields = ['q', 'status']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(code__icontains=value)
            | Q(finished_material__grade_name__icontains=value)
            | Q(finished_material__sap_material_code__icontains=value)
            | Q(customer__company_name__icontains=value)
            | Q(customer__short_name__icontains=value)
        )
