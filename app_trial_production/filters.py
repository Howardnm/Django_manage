import django_filters
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from .models import ProductionOrder, SampleInventory


class ProductionOrderFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """生产工单筛选器"""
    status = django_filters.ChoiceFilter(choices=ProductionOrder.Status.choices)
    trial_code = django_filters.CharFilter(
        field_name='trial_code', lookup_expr='icontains')
    project_name = django_filters.CharFilter(
        field_name='project__name', lookup_expr='icontains')

    class Meta:
        model = ProductionOrder
        fields = ['status', 'trial_code', 'project_name']


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
