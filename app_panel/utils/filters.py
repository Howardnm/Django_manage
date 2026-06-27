import django_filters
from django import forms
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from app_project.models import Project, ProjectNode
from common_utils.filters import DateRangeFilterMixin, TablerFilterMixin

User = get_user_model()

class PanelFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """
    全景面板过滤器
    包含日期范围筛选 (created_at) 和 用户组筛选
    """
    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='manager__groups',  # 筛选项目负责人的组
        label='用户组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '用户组'})
    )

    class Meta:
        model = Project
        fields = ['start_date', 'end_date', 'group']


class ProjectStatisticsFilter(TablerFilterMixin, django_filters.FilterSet):
    """
    项目统计专用过滤器
    """
    start_date = django_filters.DateFilter(
        label='立项开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        method='filter_init_time'
    )
    end_date = django_filters.DateFilter(
        label='立项结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        method='filter_init_time'
    )
    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='manager__groups',
        label='成员组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '成员组'})
    )
    manager = django_filters.ModelChoiceFilter(
        queryset=User.objects.all().order_by('username'),
        field_name='manager',
        label='成员',
        empty_label="所有成员",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '成员'})
    )

    class Meta:
        model = Project
        fields = ['start_date', 'end_date', 'group', 'manager']

    def filter_init_time(self, queryset, name, value):
        """
        核心逻辑：精准定位 order=1 且 stage='INIT' 的节点，使用其 updated_at 进行筛选
        """
        if not value:
            return queryset
        
        lookup = 'gte' if name == 'start_date' else 'lte'
        
        # 1. 直接在 ProjectNode 表中查找符合条件的第一个节点的项目 ID
        target_project_ids = ProjectNode.objects.filter(
            stage='INIT',
            order=1,
            **{f'updated_at__date__{lookup}': value}
        ).values_list('project_id', flat=True)
        
        # 2. 将结果限制在这些 ID 中
        return queryset.filter(id__in=target_project_ids)
