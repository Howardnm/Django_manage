import django_filters
from django import forms
from django.db.models import Q
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_raw_material.models import Supplier, RawMaterial, RawMaterialType

# 1. 供应商过滤器
class SupplierFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    class Meta:
        model = Supplier
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(sales_contact__icontains=value) |
            Q(tech_contact__icontains=value)
        )

# 2. 原材料过滤器
class RawMaterialFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    
    category = django_filters.ModelChoiceFilter(
        queryset=RawMaterialType.objects.all(),
        label='类型',
        empty_label="所有类型",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    supplier = django_filters.ModelChoiceFilter(
        queryset=Supplier.objects.all(),
        label='供应商',
        empty_label="所有供应商",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = RawMaterial
        # start_date, end_date 来自 DateRangeFilterMixin，默认筛选 created_at
        fields = ['q', 'category', 'supplier', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(model_name__icontains=value) |
            Q(warehouse_code__icontains=value)
        )

# 3. 原材料类型过滤器
class RawMaterialTypeFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('order', 'order'),
            ('name', 'name'),
            ('code', 'code'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = RawMaterialType
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(code__icontains=value) |
            Q(description__icontains=value)
        )
