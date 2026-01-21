import django_filters
from django import forms
from django.db.models import Q
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from app_process.models import MachineModel, ScrewCombination, ProcessProfile

# 2. 机台型号过滤器
class MachineModelFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    class Meta:
        model = MachineModel
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(brand__icontains=value) |
            Q(model_name__icontains=value) |
            Q(machine_code__icontains=value)
        )

# 3. 螺杆组合过滤器
class ScrewCombinationFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    
    machine = django_filters.ModelChoiceFilter(
        queryset=MachineModel.objects.all(),
        field_name='machines', # 多对多筛选
        label='适用机台',
        empty_label="所有机台",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = ScrewCombination
        fields = ['q', 'machine', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )

# 4. 工艺方案过滤器
class ProcessProfileFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    
    machine = django_filters.ModelChoiceFilter(
        queryset=MachineModel.objects.all(),
        label='适用机台',
        empty_label="所有机台",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = ProcessProfile
        fields = ['q', 'machine', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value) |
            Q(process_type_name__icontains=value)
        )
