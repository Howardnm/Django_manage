import django_filters
from django import forms
from django.contrib.auth.models import Group
from app_project.models import Project
from common_utils.filters import DateRangeFilterMixin

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
