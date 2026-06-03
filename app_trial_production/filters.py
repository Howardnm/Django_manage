import django_filters
from .models import ProductionOrder


class ProductionOrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=ProductionOrder.STATUS_CHOICES)
    trial_code = django_filters.CharFilter(
        field_name='trial_code', lookup_expr='icontains')
    project_name = django_filters.CharFilter(
        field_name='project__name', lookup_expr='icontains')

    class Meta:
        model = ProductionOrder
        fields = ['status', 'trial_code', 'project_name']
