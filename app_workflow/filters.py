import django_filters
from django import forms
from django.db.models import Q
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask


class TablerFilterMixin:
    """自动给搜索框、下拉框添加 Tabler 样式"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.filters.items():
            widget = field.field.widget
            attrs = widget.attrs
            existing_class = attrs.get('class', '')
            if field_name == 'q':
                widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': attrs.get('placeholder', '输入关键字搜索...')
                })
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                if 'form-select' not in existing_class:
                    attrs['class'] = f"{existing_class} form-select form-select-search".strip()
            elif isinstance(widget, forms.DateInput):
                if 'form-control' not in existing_class:
                    attrs['class'] = f"{existing_class} form-control".strip()
                attrs['type'] = 'date'


# ==========================================
# 1. 待办 / 已办任务筛选
# ==========================================
class WorkflowTaskFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={'placeholder': '搜索任务名称...'})
    )

    definition = django_filters.ModelChoiceFilter(
        queryset=WorkflowDefinition.objects.all().order_by('name'),
        field_name='instance__definition',
        label='所属流程',
        empty_label='所有流程',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    status = django_filters.ChoiceFilter(
        choices=[
            ('PENDING', '待处理'),
            ('COMPLETED', '已通过'),
            ('REJECTED', '已驳回'),
        ],
        label='审批结果',
        empty_label='全部状态',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    start_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        label='开始日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='lte',
        label='结束日期',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    class Meta:
        model = WorkflowTask
        fields = ['q', 'definition', 'status', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(task_name__icontains=value) |
            Q(instance__definition__name__icontains=value)
        )


# ==========================================
# 2. 我发起的流程筛选
# ==========================================
class WorkflowInstanceFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={'placeholder': '搜索流程名称...'})
    )

    definition = django_filters.ModelChoiceFilter(
        queryset=WorkflowDefinition.objects.all().order_by('name'),
        field_name='definition',
        label='所属流程',
        empty_label='所有流程',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    status = django_filters.ChoiceFilter(
        choices=WorkflowInstance.STATUS_CHOICES,
        label='流程状态',
        empty_label='全部状态',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    start_date = django_filters.DateFilter(
        field_name='started_at',
        lookup_expr='gte',
        label='发起开始',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = django_filters.DateFilter(
        field_name='started_at',
        lookup_expr='lte',
        label='发起结束',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    class Meta:
        model = WorkflowInstance
        fields = ['q', 'definition', 'status', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(definition__name__icontains=value) |
            Q(definition__description__icontains=value)
        )


# ==========================================
# 3. 流程定义筛选
# ==========================================
class WorkflowDefinitionFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={'placeholder': '搜索流程名称/描述...'})
    )

    is_active = django_filters.ChoiceFilter(
        choices=[(True, '启用中'), (False, '已禁用')],
        label='启用状态',
        empty_label='全部',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = WorkflowDefinition
        fields = ['q', 'is_active']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )
