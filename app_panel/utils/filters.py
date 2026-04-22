import django_filters
from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.db.models import Subquery, OuterRef
from app_project.models import Project, ProjectNode # 导入 ProjectNode
from common_utils.filters import DateRangeFilterMixin

User = get_user_model()

class PanelFilter(DateRangeFilterMixin, django_filters.FilterSet):
    """
    全景面板过滤器
    包含日期范围筛选 (created_at) 和 用户组筛选
    """
    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='manager__groups',  # 筛选项目负责人的组
        label='用户组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Project
        fields = ['start_date', 'end_date', 'group']


class ProjectStatisticsFilter(django_filters.FilterSet):
    """
    项目统计专用过滤器
    """
    start_date = django_filters.DateFilter(
        field_name='nodes__updated_at', # 这里的 field_name 只是一个占位符，实际过滤逻辑在 method 中
        lookup_expr='gte',
        label='立项开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        method='filter_init_time'
    )
    end_date = django_filters.DateFilter(
        field_name='nodes__updated_at', # 这里的 field_name 只是一个占位符，实际过滤逻辑在 method 中
        lookup_expr='lte',
        label='立项结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        method='filter_init_time'
    )
    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='manager__groups',
        label='成员组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    manager = django_filters.ModelChoiceFilter(
        queryset=User.objects.filter(is_staff=True).order_by('username'),
        field_name='manager',
        label='成员',
        empty_label="所有成员",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Project
        fields = ['start_date', 'end_date', 'group', 'manager']

    def filter_init_time(self, queryset, name, value):
        if not value:
            return queryset
        
        # 子查询：获取每个项目的第一个 INIT 节点的 updated_at
        # 假设 INIT 节点总是 order=1
        init_node_updated_at_subquery = ProjectNode.objects.filter(
            project=OuterRef('pk'),
            stage='INIT',
            order=1
        ).values('updated_at')[:1]

        # 为 queryset 标注一个 init_date 字段，然后基于此进行过滤
        queryset = queryset.annotate(
            init_date=Subquery(init_node_updated_at_subquery)
        )

        if name == 'start_date':
            return queryset.filter(init_date__date__gte=value).distinct()
        if name == 'end_date':
            return queryset.filter(init_date__date__lte=value).distinct()

        return queryset
