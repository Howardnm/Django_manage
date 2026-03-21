import django_filters
from django import forms
from django.db.models import Q, Subquery, OuterRef, DecimalField
from django.contrib.auth.models import Group
from app_repository.models import Customer, OEM, Salesperson, ProjectRepository
from app_repository.models import MaterialLibrary, ApplicationScenario, MaterialType, MaterialDataPoint
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin, DateRangeUpdatedFilterMixin


# 1. 项目档案列表过滤器 (修改为按项目创建日期筛选)
class ProjectRepositoryFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    customer = django_filters.ModelChoiceFilter(
        queryset=Customer.objects.all(),
        label='客户',
        empty_label="所有客户",
        widget=forms.Select(attrs={
            'class': 'form-select remote-search',
            'data-model': 'customer',
            'style': 'width: 250px;'
        })
    )

    salesperson = django_filters.ModelChoiceFilter(
        queryset=Salesperson.objects.all(),
        label='业务员',
        empty_label="所有业务员",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='project__manager__groups',
        label='所属组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # --- 新增：手动定义日期范围筛选 ---
    start_date = django_filters.DateFilter(
        field_name='project__created_at',
        lookup_expr='gte',
        label='开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = django_filters.DateFilter(
        field_name='project__created_at',
        lookup_expr='lte',
        label='结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('project__name', 'project'),
            ('updated_at', 'updated_at'),
            ('customer__company_name', 'customer'),
            ('material__grade_name', 'material'),
            ('project__created_at', 'project_created_at'), # 新增排序选项
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = ProjectRepository
        fields = ['q', 'customer', 'salesperson', 'group', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(project__name__icontains=value) |
            Q(customer__company_name__icontains=value) |
            Q(oem__name__icontains=value) |
            Q(material__grade_name__icontains=value) |
            Q(product_name__icontains=value)
        )


# 2. 客户过滤器
class CustomerFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('company_name', 'company_name'),
            ('contact_name', 'contact_name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = Customer
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(company_name__icontains=value) |
            Q(contact_name__icontains=value) |
            Q(email__icontains=value)
        )


# 3. 材料过滤器
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


# 4. 主机厂过滤器
class OEMFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('short_name', 'short_name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = OEM
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(short_name__icontains=value)
        )


# 5. 材料类型过滤器
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


# 6. 应用场景过滤器
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


# 7. 业务员过滤器
class SalespersonFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    class Meta:
        model = Salesperson
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(phone__icontains=value) |
            Q(email__icontains=value)
        )
