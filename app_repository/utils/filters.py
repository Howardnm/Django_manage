import django_filters
from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model
from app_user.models import Department
from ..models import Customer, OEM, ProjectRepository
from common_utils.filters import TablerFilterMixin
from common_utils.forms import UserPickerWidget

User = get_user_model()

# ==========================================
# 1. 项目档案列表过滤器
# ==========================================
class ProjectRepositoryFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    customer = django_filters.ModelChoiceFilter(
        queryset=Customer.objects.all(),
        label='直接客户',
        empty_label="所有客户",
        widget=forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer', 'data-placeholder': '输入客户名称搜索...'})
    )

    salesperson = django_filters.CharFilter(
        method='filter_salesperson',
        label='负责业务员',
        widget=UserPickerWidget(
            attrs={'placeholder': '点击选择业务员'},
            title='选择业务员',
            multi=False,
        )
    )

    dept = django_filters.ModelChoiceFilter(
        queryset=Department.objects.all(),
        field_name='project__manager__department',
        label='研发部门',
        empty_label="所有部门",
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '研发部门'})
    )

    start_date = django_filters.DateFilter(
        field_name='project__created_at', lookup_expr='gte', label='创建于',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('project__name', 'project'),
            ('updated_at', 'updated_at'),
            ('customer__company_name', 'customer'),
            ('project__created_at', 'created'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = ProjectRepository
        fields = ['q', 'customer', 'salesperson', 'dept', 'start_date']

    def filter_salesperson(self, queryset, name, value):
        if not value:
            return queryset
        try:
            return queryset.filter(salesperson_id=int(value))
        except (ValueError, TypeError):
            return queryset

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(project__name__icontains=value) |
            Q(customer__company_name__icontains=value) |
            Q(oem__name__icontains=value) |
            Q(product_name__icontains=value)
        )


# ==========================================
# 2. 客户公司过滤器
# ==========================================
class CustomerFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')
    account_group = django_filters.ChoiceFilter(field_name='account_group', label='客户账户组', choices=[], empty_label='客户账户组')
    customer_series = django_filters.ChoiceFilter(field_name='customer_series', label='客户系', choices=[], empty_label='客户系')
    industry = django_filters.ChoiceFilter(field_name='industry', label='行业', choices=[], empty_label='行业')
    country_name = django_filters.ChoiceFilter(field_name='country_name', label='国家名称', choices=[], empty_label='国家名称')
    sales_region = django_filters.ChoiceFilter(field_name='sales_region', label='区域', choices=[], empty_label='区域')

    sort = django_filters.OrderingFilter(
        fields=(
            ('company_name', 'company_name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = Customer
        fields = ['q', 'account_group', 'customer_series', 'industry', 'country_name', 'sales_region']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form.fields['q'].widget.attrs['placeholder'] = '检索客户编码 / 公司名称 / 搜索词'
        self.form.fields['account_group'].choices = self._account_group_choices()
        for field_name in ('customer_series', 'industry', 'country_name', 'sales_region'):
            self.form.fields[field_name].choices = self._value_choices(field_name)

    @staticmethod
    def _value_choices(field_name):
        values = (
            Customer.objects.exclude(**{field_name: ''})
            .values_list(field_name, flat=True)
            .distinct()
            .order_by(field_name)
        )
        return [(value, value) for value in values]

    @staticmethod
    def _account_group_choices():
        pairs = (
            Customer.objects.exclude(account_group='')
            .values_list('account_group', 'account_group_name')
            .distinct()
            .order_by('account_group')
        )
        return [(code, f'{code} {name}'.strip()) for code, name in pairs]

    def filter_search(self, queryset, name, value):
        """
        增强搜索：支持搜索公司名，以及关联的系统账号姓名。
        """
        return queryset.filter(
            Q(customer_code__icontains=value) |
            Q(company_name__icontains=value) |
            Q(short_name__icontains=value) |
            Q(members__first_name__icontains=value) | # 搜索关联人的姓名
            Q(members__username__icontains=value)    # 搜索关联人的账号
        ).distinct()


# ==========================================
# 3. 主机厂过滤器
# ==========================================
class OEMFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    sort = django_filters.OrderingFilter(
        fields=(
            ('name', 'name'),
            ('short_name', 'short_name'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = OEM
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(short_name__icontains=value) |
            Q(members__first_name__icontains=value)
        ).distinct()
