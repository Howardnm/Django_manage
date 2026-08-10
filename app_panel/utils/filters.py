import django_filters
from django import forms
from app_project.models import Project, ProjectNode
from app_user.models import Subsidiary, WorkGroup
from common_utils.filters import DateRangeFilterMixin, TablerFilterMixin
from common_utils.forms import UserPickerWidget

class PanelFilter(TablerFilterMixin, DateRangeFilterMixin, django_filters.FilterSet):
    """
    全景面板过滤器
    包含日期范围筛选 (created_at)、子公司基地筛选 和 工作组筛选
    """
    subsidiary = django_filters.ModelChoiceFilter(
        queryset=Subsidiary.objects.all(),
        field_name='manager__subsidiary',
        label='子公司基地',
        empty_label="全部子公司",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '子公司基地'})
    )
    workgroup = django_filters.ModelChoiceFilter(
        queryset=WorkGroup.objects.all(),
        field_name='manager__work_groups',
        label='工作组',
        empty_label="全部工作组",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '工作组'})
    )

    class Meta:
        model = Project
        fields = ['start_date', 'end_date', 'subsidiary', 'workgroup']


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
    subsidiary = django_filters.ModelChoiceFilter(
        queryset=Subsidiary.objects.all(),
        field_name='manager__subsidiary',
        label='子公司基地',
        empty_label="全部子公司",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '子公司基地'})
    )
    workgroup = django_filters.ModelChoiceFilter(
        queryset=WorkGroup.objects.all(),
        field_name='manager__work_groups',
        label='工作组',
        empty_label="全部工作组",
        widget=forms.Select(attrs={'class': 'form-select form-select-search', 'placeholder': '工作组'})
    )
    manager = django_filters.CharFilter(
        method='filter_manager',
        label='成员',
        widget=UserPickerWidget(
            attrs={'placeholder': '点击选择成员'},
            title='选择成员',
            multi=False,
        ),
    )

    class Meta:
        model = Project
        fields = ['start_date', 'end_date', 'subsidiary', 'workgroup', 'manager']

    def filter_manager(self, queryset, name, value):
        if not value:
            return queryset
        try:
            return queryset.filter(manager_id=int(value))
        except (ValueError, TypeError):
            return queryset

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
