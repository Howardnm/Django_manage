import django_filters
from django import forms
from django.db.models import Q
from django.contrib.auth.models import Group
from ..models import Customer, OEM, Salesperson, ProjectRepository # 修正导入路径
from common_utils.filters import TablerFilterMixin


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
            ('project__created_at', 'project_created_at'),
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
