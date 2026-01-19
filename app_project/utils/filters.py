import django_filters
from django.db.models import Q
from django import forms
from django.contrib.auth.models import Group  # 【新增】
from app_project.models import Project, ProjectNode, ProjectStage
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin


class ProjectFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    # 1. 搜索框
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '搜名称/负责人/描述...'
        })
    )

    # 2. 排序
    sort = django_filters.OrderingFilter(
        fields=(
            ('created_at', 'created_at'),
            ('name', 'name'),
            ('manager__username', 'manager'),
            ('current_stage', 'stage'),
        ),
        field_labels={
            'created_at': '创建时间',
            'name': '项目名称',
            'current_stage': '当前阶段',
        },
        widget=forms.HiddenInput
    )

    # 3. 负责人筛选
    manager = django_filters.ChoiceFilter(
        method='filter_manager',
        label='负责人',
        choices=[('me', '只看我的')],
        empty_label="所有负责人",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 4. 阶段筛选
    stage = django_filters.ChoiceFilter(
        field_name='current_stage',
        choices=ProjectStage.choices,
        label='当前阶段',
        empty_label="所有阶段",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    # 5. 【新增】用户组筛选
    group = django_filters.ModelChoiceFilter(
        queryset=Group.objects.all(),
        field_name='manager__groups',  # 筛选项目负责人的组
        label='所属组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Project
        # start_date, end_date 来自 DateRangeFilterMixin
        fields = ['q', 'manager', 'group', 'stage', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(manager__username__icontains=value) |
            Q(description__icontains=value)
        )

    def filter_manager(self, queryset, name, value):
        if value == 'me':
            return queryset.filter(manager=self.request.user)
        return queryset
