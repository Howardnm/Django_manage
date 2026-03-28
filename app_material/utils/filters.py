import django_filters
from django import forms
from django.db.models import Q, Subquery, OuterRef, DecimalField

from app_material.models import ApplicationScenario, MaterialType, MaterialLibrary, MaterialDataPoint
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin


class MaterialFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    scenarios = django_filters.ModelMultipleChoiceFilter(
        queryset=ApplicationScenario.objects.all(),
        widget=forms.SelectMultiple(attrs={
            'class': 'form-select remote-search tomselect-multi-remote',
            'data-model': 'applicationscenario'
        }),
        conjoined=False
    )

    category = django_filters.ModelChoiceFilter(
        queryset=MaterialType.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    melt_min = django_filters.NumberFilter(method='filter_metric', label='熔指 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    melt_max = django_filters.NumberFilter(method='filter_metric', label='熔指 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))

    tensile_min = django_filters.NumberFilter(method='filter_metric', label='拉伸 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    tensile_max = django_filters.NumberFilter(method='filter_metric', label='拉伸 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))

    flex_modulus_min = django_filters.NumberFilter(method='filter_metric', label='弯模 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    flex_modulus_max = django_filters.NumberFilter(method='filter_metric', label='弯模 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))

    impact_min = django_filters.NumberFilter(method='filter_metric', label='冲击 Min', widget=forms.NumberInput(attrs={'placeholder': 'Min', 'class': 'form-control form-control-sm'}))
    impact_max = django_filters.NumberFilter(method='filter_metric', label='冲击 Max', widget=forms.NumberInput(attrs={'placeholder': 'Max', 'class': 'form-control form-control-sm'}))

    sort = django_filters.OrderingFilter(
        fields=(
            ('grade_name', 'grade_name'),
            ('manufacturer', 'manufacturer'),
            ('created_at', 'created_at'),
            ('val_density', 'density'),
            ('val_ash', 'ash'),
            ('val_melt', 'melt_index'),
            ('val_tensile', 'tensile'),
            ('val_flex_strength', 'flex_strength'),
            ('val_flex_modulus', 'flex_modulus'),
            ('val_impact', 'impact'),
            ('val_hdt', 'hdt'),
            ('flammability', 'flammability'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = MaterialLibrary
        fields = ['q', 'category', 'scenarios', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(grade_name__icontains=value) | Q(manufacturer__icontains=value)
        )

    def filter_metric(self, queryset, name, value):
        if value is None:
            return queryset

        parts = name.split('_')
        operator = parts[-1]
        metric_key = '_'.join(parts[:-1])

        keyword_map = {
            'melt': '熔融',
            'tensile': '拉伸强度',
            'flex_modulus': '弯曲模量',
            'impact': '冲击',
        }
        keyword = keyword_map.get(metric_key)
        if not keyword:
            return queryset

        std = 'ISO'
        if hasattr(self, 'request') and self.request:
            std = self.request.GET.get('std', 'ISO')

        subquery = Subquery(
            MaterialDataPoint.objects.filter(
                material=OuterRef('pk'),
                test_config__name__icontains=keyword,
                test_config__standard__icontains=std
            ).values('value')[:1],
            output_field=DecimalField()
        )

        temp_field = f"_filter_{name}"
        queryset = queryset.annotate(**{temp_field: subquery})

        lookup = 'gte' if operator == 'min' else 'lte'
        filter_kwargs = {f"{temp_field}__{lookup}": value}

        return queryset.filter(**filter_kwargs)


class MaterialTypeFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    classification = django_filters.ChoiceFilter(
        choices=MaterialType.CLASSIFICATION_CHOICES,
        label='塑料归类',
        empty_label="所有归类",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('classification', 'classification'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = MaterialType
        fields = ['q', 'classification']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )


class ScenarioFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = ApplicationScenario
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(requirements__icontains=value)
        )
