import django_filters
from django import forms
from django.db.models import Q
from django.contrib.auth.models import Group  # 【新增】
from app_repository.models import Customer, OEM, Salesperson, ProjectRepository
from app_repository.models import MaterialLibrary, ApplicationScenario, MaterialType
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin, DateRangeUpdatedFilterMixin


# 1. 项目档案列表过滤器 (使用 Updated 时间)
class ProjectRepositoryFilter(TablerFilterMixin, DateRangeUpdatedFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    customer = django_filters.ModelChoiceFilter(
        queryset=Customer.objects.all(),
        label='客户',
        empty_label="所有客户",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    salesperson = django_filters.ModelChoiceFilter(
        queryset=Salesperson.objects.all(),
        label='业务员',
        empty_label="所有业务员",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 【新增】用户组筛选 (筛选项目负责人的组)
    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='project__manager__groups',  # 注意这里的跨表查询路径
        label='所属组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('project__name', 'project'),
            ('updated_at', 'updated_at'),
            ('customer__company_name', 'customer'),
            ('material__grade_name', 'material'),
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


# 2. 客户过滤器 (使用 Created 时间 - 假设 Customer 有 created_at，如果没有可以去掉 DateRangeFilterMixin)
# 假设 Customer 没有 created_at 字段，或者我们不关心时间筛选，这里只用 TablerFilterMixin
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


# 3. 材料过滤器 (使用 Created 时间)
class MaterialFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    scenarios = django_filters.ModelMultipleChoiceFilter(
        queryset=ApplicationScenario.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-search'}),
        conjoined=False
    )

    category = django_filters.ModelChoiceFilter(
        queryset=MaterialType.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('grade_name', 'grade_name'),
            ('manufacturer', 'manufacturer'),
            ('created_at', 'created_at'),
            ('val_density', 'density'),
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

    sort = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = MaterialType
        fields = ['q']

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
