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

    sort = django_filters.OrderingFilter(
        fields=(
            ('company_name', 'company_name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = Customer
        fields = ['q']

    def filter_search(self, queryset, name, value):
        """
        增强搜索：支持搜索公司名，以及关联的系统账号姓名。
        """
        return queryset.filter(
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
