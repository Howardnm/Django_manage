from django.shortcuts import render
from django.views import View

from app_panel.mixins import (
    PanelAccessMixin,
    WorkspaceFormCardMixin,
    WorkspaceWorkflowCardMixin,
)

MAX_ITEMS = 8  # 每张卡片最多展示的记录数（紧凑型卡片可容纳更多）


class PersonalWorkspaceView(PanelAccessMixin, View):
    """个人工作台：当前用户的表单、流程、待办、已办概览。

    L1/L2: PanelAccessMixin (module_code='panel') 从 DB 读取。
    L3: 显式声明 [] — 跨模块聚合视图，卡片级鉴权由 Workspace*CardMixin 在 get() 中执行。
    """

    permission_required = []  # 跨模块聚合，卡片级鉴权在 get() 中执行

    def get(self, request):
        user = request.user
        context = {}

        # ── 卡片级权限检查（由 app_panel/mixins.py 统一管理）──
        has_form = WorkspaceFormCardMixin.user_has_form_access(user)
        has_workflow = WorkspaceWorkflowCardMixin.user_has_workflow_access(user)

        # ── Auth-Before-Query：仅对通过鉴权的模块查询 ──
        if has_form:
            from app_form_management.models import FormSubmission
            from app_form_management.registry import resolve_form_target

            # 草稿（最近 5 条，按更新时间倒序）
            recent_drafts = list(
                FormSubmission.objects
                .filter(submitted_by=user, status='DRAFT')
                .select_related('template', 'content_type')
                .order_by('-updated_at')[:MAX_ITEMS]
            )
            for d in recent_drafts:
                d.target_module, d.target_display, d.target_url = resolve_form_target(d)
            context['recent_drafts'] = recent_drafts
            context['draft_count'] = (
                FormSubmission.objects.filter(submitted_by=user, status='DRAFT').count()
            )

            # 已提交（最近 5 条）
            recent_submissions = list(
                FormSubmission.objects
                .filter(submitted_by=user, status='SUBMITTED')
                .select_related('template', 'workflow_instance__definition', 'content_type')
                .order_by('-created_at')[:MAX_ITEMS]
            )
            for s in recent_submissions:
                s.target_module, s.target_display, s.target_url = resolve_form_target(s)
            context['recent_submissions'] = recent_submissions
            context['submission_count'] = (
                FormSubmission.objects.filter(submitted_by=user, status='SUBMITTED').count()
            )

        if has_workflow:
            from app_workflow.models import WorkflowInstance, WorkflowTask
            from app_workflow.utils import related_object_router, _batch_resolve_content_objects
            from app_form_management.models import FormSubmission

            # 我发起的流程（最近 5 条）
            recent_instances = list(
                WorkflowInstance.objects
                .filter(started_by=user)
                .select_related('definition', 'content_type')
                .prefetch_related('tasks')
                .order_by('-started_at')[:MAX_ITEMS]
            )
            _batch_resolve_content_objects(recent_instances)
            for inst in recent_instances:
                obj = getattr(inst, '_content_object', None)
                inst.related_model_name = obj._meta.verbose_name if obj else None
                inst.related_display_name = related_object_router.get_display_name(obj)
                inst.related_object_url = related_object_router.resolve(obj)
                # 关联内容是表单时，点击应直达表单审批页（而非流程实例页）
                inst.is_form_related = isinstance(obj, FormSubmission)
            context['recent_instances'] = recent_instances
            context['initiated_count'] = (
                WorkflowInstance.objects.filter(started_by=user).count()
            )

            # 待办任务（最近 5 条）
            pending_tasks = list(
                WorkflowTask.objects
                .filter(assigned_to=user, status='PENDING')
                .select_related('instance__definition', 'instance__started_by')
                .order_by('-created_at')[:MAX_ITEMS]
            )
            context['pending_tasks'] = pending_tasks
            context['pending_count'] = (
                WorkflowTask.objects.filter(
                    assigned_to=user, status='PENDING'
                ).count()
            )

            # 已办任务（最近 5 条）
            completed_tasks = list(
                WorkflowTask.objects
                .filter(
                    assigned_to=user,
                    status__in=['COMPLETED', 'REJECTED', 'CANCELED']
                )
                .select_related('instance__definition')
                .order_by('-completed_at')[:MAX_ITEMS]
            )
            context['completed_tasks'] = completed_tasks
            context['completed_count'] = (
                WorkflowTask.objects.filter(
                    assigned_to=user,
                    status__in=['COMPLETED', 'REJECTED', 'CANCELED']
                ).count()
            )

            # 解析待办/已办任务关联的流程实例 content_object（去重批量获取，避免 N+1）
            task_instances = [
                t.instance
                for t in (pending_tasks + completed_tasks)
                if t.instance.content_type_id
            ]
            _batch_resolve_content_objects(task_instances)
            for task in pending_tasks + completed_tasks:
                obj = getattr(task.instance, '_content_object', None)
                task.related_model_name = obj._meta.verbose_name if obj else None
                task.related_display_name = related_object_router.get_display_name(obj)
                task.related_object_url = related_object_router.resolve(obj)
                # 关联内容是表单时，点击应直达表单审批页（而非流程实例页）
                task.is_form_related = isinstance(obj, FormSubmission)

        context['has_form'] = has_form
        context['has_workflow'] = has_workflow
        return render(request, 'apps/app_panel/personal_workspace.html', context)
