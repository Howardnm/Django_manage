from urllib.parse import quote

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import (
    Project, ProjectNode, ProjectMember, ProjectSalesMember, NodeScoreRule,
    ProjectConfig, ProjectFieldChange, MemberScoreSnapshot, FailureReason,
    FeedbackType, BusinessSegment, ProjectStage,
)


class _DashReasonWidget(forms.Widget):
    """普通节点没有原因。不输出 input，避免随表单提交空值。"""

    def render(self, name, value, attrs=None, renderer=None):
        return mark_safe('<span class="quiet">—</span>')


class ProjectNodeInlineForm(forms.ModelForm):
    """压缩备注框。默认 Admin textarea 10 行，一个项目约 7 个节点会把表格撑得过长。

    「原因」不是模型字段。按该行已保存的状态/阶段决定下拉：
    异常节点写不合格原因，客户意见写意见类型，其余行只显示破折号。
    """

    reason = forms.CharField(required=False, label='原因')

    class Meta:
        model = ProjectNode
        fields = '__all__'
        widgets = {
            'remark': forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 以库里的状态为准。同一轮把普通节点改成异常/客户意见后，下拉要刷新才出现。
        self.reason_kind = self._reason_kind(self.instance)
        if self.reason_kind == 'failure':
            self.fields['reason'] = self._reason_choice(
                FailureReason, self.instance.failure_reason_id,
            )
        elif self.reason_kind == 'feedback':
            self.fields['reason'] = self._reason_choice(
                FeedbackType, self.instance.feedback_type_id,
            )
        else:
            self.fields['reason'].disabled = True
            self.fields['reason'].widget = _DashReasonWidget()

    @staticmethod
    def _reason_kind(node):
        if node.status == 'FAILED':
            return 'failure'
        if node.status == 'FEEDBACK' or node.stage == ProjectStage.FEEDBACK:
            return 'feedback'
        return None

    @staticmethod
    def _reason_choice(model, current_id):
        query = Q(is_active=True)
        if current_id:
            query |= Q(pk=current_id)
        return forms.ModelChoiceField(
            queryset=model.objects.filter(query).order_by('order', 'name'),
            required=False,
            label='原因',
            empty_label='-- 请选择 --',
            initial=current_id,
        )

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.reason_kind == 'failure':
            obj.failure_reason = self.cleaned_data.get('reason')
        elif self.reason_kind == 'feedback':
            obj.feedback_type = self.cleaned_data.get('reason')
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class ProjectNodeInline(admin.TabularInline):
    model = ProjectNode
    form = ProjectNodeInlineForm
    extra = 0
    fields = ['stage', 'status', 'reason', 'round', 'order', 'final_score', 'remark', 'updated_at']
    readonly_fields = ['updated_at']

class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 1

class ProjectSalesMemberInline(admin.TabularInline):
    model = ProjectSalesMember
    extra = 1

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'manager', 'current_stage', 'progress_percent', 'is_terminated', 'created_at']
    list_filter = ['current_stage', 'is_terminated', 'manager']
    search_fields = ['code', 'name', 'description']
    search_help_text = '项目编码 / 项目名称 / 描述'
    inlines = [ProjectMemberInline, ProjectSalesMemberInline, ProjectNodeInline]
    change_list_template = 'admin/app_project/project/change_list.html'

    def get_urls(self):
        custom = [
            path(
                'export/',
                self.admin_site.admin_view(self.export_projects_view),
                name='app_project_project_export',
            ),
        ]
        return custom + super().get_urls()

    def get_deleted_objects(self, objs, request):
        """变更记录不许在自己的菜单里删，但不挡住随项目级联删除。"""
        deleted_objects, model_count, perms_needed, protected = super().get_deleted_objects(
            objs, request,
        )
        field_change_label = str(ProjectFieldChange._meta.verbose_name)
        perms_needed = {
            name for name in perms_needed if str(name) != field_change_label
        }
        return deleted_objects, model_count, perms_needed, protected

    def export_projects_view(self, request):
        """现查现组，字节放进响应。不写盘，也不把表留在 admin 实例上。"""
        if not self.has_view_permission(request):
            raise PermissionDenied
        from .utils.project_export import build_project_export

        payload = build_project_export()
        filename = f"项目导出-{timezone.localdate():%Y%m%d}.xlsx"
        response = HttpResponse(
            payload,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f"attachment; filename*=UTF-8''{quote(filename)}"
        return response

    def save_formset(self, request, form, formset, change):
        """inline 成员/节点保存后，兜底重算本项目成绩并写成员快照。

        绕过「父对象表单保存 vs inline 信号回写」的旧值覆盖竞态。
        """
        super().save_formset(request, form, formset, change)
        project = form.instance
        if project and project.pk:
            from .utils.signals import recalculate_project_scores
            try:
                recalculate_project_scores(project)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "admin save_formset 重算失败 project=%s", project.pk
                )

@admin.register(NodeScoreRule)
class NodeScoreRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'score_value', 'trigger_stage', 'trigger_status', 'is_multiple_rounds']
    list_filter = ['trigger_status', 'trigger_stage', 'is_multiple_rounds']
    search_fields = ['name', 'description']

@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'role', 'workload_share']
    list_filter = ['role', 'user']


@admin.register(ProjectConfig)
class ProjectConfigAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'node_workflow_display', 'repo_workflow_display', 'edit_workflow_display']

    def has_add_permission(self, request):
        return not ProjectConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """禁止删除"""
        return False

    def node_workflow_display(self, obj):
        if obj.default_approval_workflow:
            return format_html(
                '<span class="badge bg-blue-lt">{}</span>',
                obj.default_approval_workflow.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（节点操作无需审批）</span>')
    node_workflow_display.short_description = '项目节点审批流程'

    def repo_workflow_display(self, obj):
        if obj.default_repository_approval_workflow:
            return format_html(
                '<span class="badge bg-green-lt">{}</span>',
                obj.default_repository_approval_workflow.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（档案编辑直接生效）</span>')
    repo_workflow_display.short_description = '项目档案审批流程'

    def edit_workflow_display(self, obj):
        if obj.default_project_edit_approval_workflow:
            return format_html(
                '<span class="badge bg-orange-lt">{}</span>',
                obj.default_project_edit_approval_workflow.name
            )
        return mark_safe('<span class="badge bg-secondary-lt">未配置（信息编辑直接生效）</span>')
    edit_workflow_display.short_description = '项目信息编辑审批流程'


@admin.register(ProjectFieldChange)
class ProjectFieldChangeAdmin(admin.ModelAdmin):
    list_display = ['project', 'status_badge', 'submitted_by', 'submission_comment_preview', 'created_at', 'resolved_at']
    list_filter = ['status', 'created_at']
    search_fields = ['project__name', 'submission_comment']
    readonly_fields = ['project', 'code', 'name', 'grade', 'material', 'description',
                       'submitted_by', 'submission_comment', 'status', 'workflow_instance',
                       'created_at', 'resolved_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def status_badge(self, obj):
        color_map = {'PENDING': 'bg-purple-lt', 'APPROVED': 'bg-green-lt', 'REJECTED': 'bg-red-lt'}
        css = color_map.get(obj.status, 'bg-secondary-lt')
        return format_html('<span class="badge {}">{}</span>', css, obj.get_status_display())
    status_badge.short_description = '状态'

    def submission_comment_preview(self, obj):
        return obj.submission_comment[:50] + '…' if len(obj.submission_comment) > 50 else obj.submission_comment
    submission_comment_preview.short_description = '提交意见'


class _LookupAdmin(admin.ModelAdmin):
    """名称 / 编码 / 排序 / 说明 / 是否启用，三个字典共用。"""

    list_display = ['name', 'code', 'order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code']
    ordering = ['order', 'name']


@admin.register(FailureReason)
class FailureReasonAdmin(_LookupAdmin):
    pass


@admin.register(FeedbackType)
class FeedbackTypeAdmin(_LookupAdmin):
    pass


@admin.register(BusinessSegment)
class BusinessSegmentAdmin(_LookupAdmin):
    pass


@admin.register(MemberScoreSnapshot)
class MemberScoreSnapshotAdmin(admin.ModelAdmin):
    """成员成绩快照由计分信号写入。后台可批量删除以便重建，不能手改分数。"""

    list_display = [
        'project', 'user', 'track', 'effective_score', 'workload_score',
        'quality_score', 'workload_share', 'grade_factor', 'snapshot_at',
    ]
    list_filter = ['track', 'snapshot_at']
    search_fields = ['project__name', 'user__username']
    ordering = ['-snapshot_at', '-pk']
    readonly_fields = [
        'project', 'user', 'track', 'snapshot_at',
        'effective_score', 'workload_score',
        'quality_score', 'workload_share', 'grade_factor',
    ]
    actions = ['delete_selected']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
