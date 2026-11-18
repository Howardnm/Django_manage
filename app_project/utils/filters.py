from datetime import timedelta

import django_filters
from django.db.models import OuterRef, Q, Subquery
from django import forms
from django.utils import timezone
from django.contrib.auth import get_user_model
from app_user.models import WorkGroup
from app_project.models import Project, ProjectNode, ProjectStage, BusinessSegment
from common_utils.filters import TablerFilterMixin, DateRangeFilterMixin
from common_utils.forms import UserPickerWidget

User = get_user_model()

# 与 Project.current_active_node 同一口径：按顺序第一个未结束节点。
_ACTIVE_NODE_STATUSES = ('DOING', 'PENDING', 'PAUSED', 'AWAITING_APPROVAL')


def filter_project_run_status(queryset, name, value):
    """正常项目 / 已暂停 / 已终止。传函数而不是方法名，避免 FilterSet 按名字查找失败。"""
    if value == 'terminated':
        return queryset.filter(is_terminated=True)
    active_status = ProjectNode.objects.filter(
        project=OuterRef('pk'),
        status__in=_ACTIVE_NODE_STATUSES,
    ).order_by('order').values('status')[:1]
    queryset = queryset.filter(is_terminated=False).annotate(
        _active_status=Subquery(active_status),
    )
    if value == 'paused':
        return queryset.filter(_active_status='PAUSED')
    if value == 'doing':
        return queryset.exclude(_active_status='PAUSED')
    return queryset


def filter_stale_days(queryset, name, value):
    """未终止且未完成，当前节点 updated_at 早于 N 天。口径同全景看板停滞预警。"""
    if value is None or value < 1:
        return queryset
    cutoff = timezone.now() - timedelta(days=int(value))
    current_updated = Subquery(
        ProjectNode.objects.filter(project=OuterRef('pk'))
        .exclude(status__in=('DONE', 'FAILED', 'FEEDBACK'))
        .order_by('order')
        .values('updated_at')[:1]
    )
    return (
        queryset.filter(is_terminated=False, progress_percent__lt=100)
        .annotate(_current_node_updated_at=current_updated)
        .filter(_current_node_updated_at__lt=cutoff)
    )


class ProjectFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    # 1. 搜索框
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '搜名称/编号/客户/产品'
        })
    )

    # 排序（隐藏，不占筛选栏位置）
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

    # 2. 负责人筛选（组织架构树选择器）
    manager = django_filters.CharFilter(
        method='filter_manager',
        label='负责人',
        widget=UserPickerWidget(
            attrs={'placeholder': '点击选择负责人'},
            title='选择负责人',
            multi=False,
        )
    )

    # 3. 工作组筛选 (L5 数据资产隔离)
    group = django_filters.ModelChoiceFilter(
        queryset=WorkGroup.objects.all(),
        field_name='manager__work_groups',
        label='工作组',
        empty_label="所有组",
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '工作组'})
    )

    # 4. 业务板块筛选
    business_segment = django_filters.ModelChoiceFilter(
        queryset=BusinessSegment.objects.all(),
        field_name='business_segment',
        label='业务板块',
        empty_label="所有板块",
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '业务板块'})
    )

    # 5. 阶段筛选
    stage = django_filters.ChoiceFilter(
        field_name='current_stage',
        choices=ProjectStage.choices,
        label='当前阶段',
        empty_label="所有阶段",
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '当前阶段'})
    )

    # 6. 项目状态：正常项目 / 已暂停 / 已终止
    run_status = django_filters.ChoiceFilter(
        method=filter_project_run_status,
        choices=(
            ('doing', '正常项目'),
            ('paused', '已暂停'),
            ('terminated', '已终止'),
        ),
        label='项目状态',
        empty_label='项目状态',
        widget=forms.Select(attrs={'class': 'form-select', 'placeholder': '项目状态'}),
    )

    # 7. 当前节点停滞天数
    stale_days = django_filters.NumberFilter(
        method=filter_stale_days,
        label='项目停滞天数',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '项目停滞天数',
            'min': '1',
            'step': '1',
        }),
    )

    class Meta:
        model = Project
        fields = ['q', 'manager', 'group', 'business_segment', 'stage', 'run_status', 'stale_days', 'start_date', 'end_date']

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
            Q(code__icontains=value) |
            Q(repository__customer__company_name__icontains=value) |
            Q(repository__customer__short_name__icontains=value) |
            Q(repository__product_name__icontains=value)
        )
