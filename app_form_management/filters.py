import django_filters
from django import forms
from django.db.models import Q
from .models import FormTemplate, FormSubmission
from app_workflow.models import WorkflowDefinition, WorkflowInstance


class TablerFilterMixin:
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
# 1. 表单模板筛选
# ==========================================
class FormTemplateFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={'placeholder': '搜索模板名称/描述...'})
    )

    is_active = django_filters.ChoiceFilter(
        choices=[(True, '启用中'), (False, '已禁用')],
        label='启用状态',
        empty_label='全部',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    workflow = django_filters.ModelChoiceFilter(
        queryset=WorkflowDefinition.objects.all().order_by('name'),
        label='关联审批流程',
        empty_label='全部',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = FormTemplate
        fields = ['q', 'is_active', 'workflow']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )


# ==========================================
# 2. 我的草稿筛选
# ==========================================
class MyDraftsFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={'placeholder': '搜索模板名称...'})
    )

    template = django_filters.ModelChoiceFilter(
        queryset=FormTemplate.objects.all().order_by('name'),
        label='表单模板',
        empty_label='全部',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = FormSubmission
        fields = ['q', 'template']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(template__name__icontains=value) |
            Q(remark__icontains=value)
        )


# ==========================================
# 3. 我的提交记录筛选
# ==========================================
class MySubmissionsFilter(TablerFilterMixin, django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='搜索',
        widget=forms.TextInput(attrs={'placeholder': '搜索模板名称...'})
    )

    template = django_filters.ModelChoiceFilter(
        queryset=FormTemplate.objects.all().order_by('name'),
        label='表单模板',
        empty_label='全部',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    workflow_status = django_filters.ChoiceFilter(
        choices=[
            ('has_workflow', '有审批流程'),
            ('RUNNING', '运行中'),
            ('COMPLETED', '已完成'),
            ('REJECTED', '已拒绝'),
            ('CANCELED', '已取消'),
        ],
        method='filter_workflow_status',
        label='流程进度',
        empty_label='全部',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    start_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte',
        label='提交开始',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    end_date = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='lte',
        label='提交结束',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

    class Meta:
        model = FormSubmission
        fields = ['q', 'template', 'workflow_status', 'start_date', 'end_date']

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(template__name__icontains=value) |
            Q(remark__icontains=value)
        )

    def filter_workflow_status(self, queryset, name, value):
        if not value:
            return queryset
        if value == 'has_workflow':
            return queryset.filter(workflow_instance__isnull=False)
        return queryset.filter(workflow_instance__status=value)
