import django_filters
from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model
from app_user.models import Department
from ..models import Customer, OEM, ProjectRepository
from common_utils.filters import TablerFilterMixin

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
        widget=forms.Select(attrs={'class': 'form-select remote-search', 'data-model': 'customer'})
    )

    # 业务员筛选：精准匹配 SALES 角色
    salesperson = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(user_type=User.UserType.SALES),
        label='负责业务员',
        empty_label="所有人员",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 部门筛选：对应 app_user.Department
    dept = django_filters.ModelChoiceFilter(
        queryset=Department.objects.all(),
        field_name='project__manager__department',
        label='研发部门',
        empty_label="所有部门",
        widget=forms.Select(attrs={'class': 'form-select'})
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
