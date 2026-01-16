import django_filters
from django import forms
from django.db.models import Q
from app_repository.models import Customer, MaterialLibrary, MaterialType, ApplicationScenario, OEM, Salesperson, ProjectRepository


class TablerFilterMixin:
    """定义通用的搜索框样式，避免重复写 widget"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 给搜索框 q 加上 form-control
        if 'q' in self.filters:
            self.filters['q'].field.widget.attrs.update({
                'class': 'form-control',
                'placeholder': '输入关键字搜索...'
            })


# 1. 项目档案列表过滤器
class ProjectRepositoryFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    # 支持按业务员筛选
    customer = django_filters.ModelChoiceFilter(
        queryset=Customer.objects.all(),
        label='客户',
        empty_label="所有客户",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 支持按业务员筛选
    salesperson = django_filters.ModelChoiceFilter(
        queryset=Salesperson.objects.all(),
        label='业务员',
        empty_label="所有业务员",
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
        fields = ['q']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(project__name__icontains=value) |
            Q(customer__company_name__icontains=value) |
            Q(oem__name__icontains=value) |
            Q(material__grade_name__icontains=value) |
            Q(product_name__icontains=value)
        )


# 1. 客户过滤器
class CustomerFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    # 排序字段
    sort = django_filters.OrderingFilter(
        fields=(
            ('company_name', 'company_name'),
            ('contact_name', 'contact_name'),
            ('id', 'id'),
        ),
        widget=forms.HiddenInput  # 隐藏控件
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


# 2. 材料过滤器
class MaterialFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(method='filter_search', label='搜索')

    # 筛选：按类型 (自动生成下拉框)
    category = django_filters.ModelChoiceFilter(
        queryset=MaterialType.objects.all(),
        label='材料类型',
        empty_label="所有类型",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 筛选：按应用场景
    # 【修改】使用 ModelMultipleChoiceFilter 支持多选筛选
    # conjoined=False 表示“或者”关系（包含 A 或 B 均可）
    # conjoined=True 表示“并且”关系（必须同时包含 A 和 B）
    # 这里通常用 False，即筛选出“适用于汽车”的所有材料
    scenarios = django_filters.ModelMultipleChoiceFilter(
        queryset=ApplicationScenario.objects.all(),
        label='应用场景',
        widget=forms.SelectMultiple(attrs={'class': 'form-select form-select-search'}),
        conjoined=False
    )

    sort = django_filters.OrderingFilter(
        fields=(
            ('grade_name', 'grade_name'),
            ('category__name', 'category_name'),
            # 物理
            ('melt_index', 'melt_index'),
            # 机械
            ('tensile_strength', 'tensile'),
            ('flexural_strength', 'flex_strength'),
            ('flexural_modulus', 'flex_modulus'),
            ('izod_impact_23', 'impact_23'),
            # 热学
            ('hdt_045', 'hdt_045'),  # HDT 主要按这个排
            ('hdt_180', 'hdt_180'),
            # 阻燃
            ('flammability', 'flammability'),
            # 【新增】支持按时间排序
            ('created_at', 'created_at'),
        ),
        widget=forms.HiddenInput
    )

    class Meta:
        model = MaterialLibrary
        fields = ['q', 'category', 'scenarios']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(grade_name__icontains=value) |
            Q(manufacturer__icontains=value)
        )


# 3. 主机厂过滤器
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


# 1. 材料类型过滤器
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


# 2. 应用场景过滤器
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


# 【新增】业务员过滤器
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
