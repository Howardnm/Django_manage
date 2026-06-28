import django_filters
from django.db.models import Q
from django import forms
from django.contrib.auth import get_user_model
from app_user.models import WorkGroup
from app_project.models import Project, ProjectNode, ProjectStage
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from common_utils.forms import UserPickerWidget

User = get_user_model()

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

    # 3. 负责人筛选（组织架构树选择器）
    manager = django_filters.CharFilter(
        method='filter_manager',
        label='负责人',
        widget=UserPickerWidget(
            attrs={'placeholder': '点击选择负责人'},
            title='选择负责人',
            multi=False,
        )
    )

    # 4. 阶段筛选
    stage = django_filters.ChoiceFilter(
        field_name='current_stage',
        choices=ProjectStage.choices,
        label='当前阶段',
        empty_label="所有阶段",
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '当前阶段'})
    )

    # 5. 工作组筛选 (L5 数据资产隔离)
    group = django_filters.ModelChoiceFilter(
        queryset=WorkGroup.objects.all(),
        field_name='manager__work_groups',
        label='工作组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '工作组'})
    )

    class Meta:
        model = Project
        fields = ['q', 'manager', 'group', 'stage', 'start_date', 'end_date']

    def filter_manager(self, queryset, name, value):
        if not value:
            return queryset
        try:
            return queryset.filter(manager_id=int(value))
        except (ValueError, TypeError):
            return queryset

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(manager__username__icontains=value) |
            Q(description__icontains=value)
        )
