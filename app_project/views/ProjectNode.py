from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.db import transaction
from django.contrib import messages

from app_project.forms import ProjectNodeUpdateForm
from app_project.mixins import ProjectAccessMixin
from app_project.models import ProjectNode
from app_workflow.utils import WorkflowEngine


# ==========================================
# 4. 节点操作：常规更新
# ==========================================
class ProjectNodeUpdateView(ProjectAccessMixin, View):
    """常规更新：需有 change_project 权限"""
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_progress_update.html'

    def get_node_and_check_perm(self, pk):
        """辅助方法：获取节点并检查项目级权限"""
        node = get_object_or_404(ProjectNode, pk=pk)
        # 统一检查“能否动这个项目” (负责人/同部门/协同成员)
        self.check_object_permission(node.project)
        return node

    def get(self, request, pk):
        node = self.get_node_and_check_perm(pk)
        form = ProjectNodeUpdateForm(instance=node)

        return render(request, self.template_name, {
            'node': node,
            'form': form,
        })

    def post(self, request, pk):
        node = self.get_node_and_check_perm(pk)
        form = ProjectNodeUpdateForm(request.POST, instance=node)

        if form.is_valid():
            with transaction.atomic():
                new_status = form.cleaned_data.get('status')

                # --- 优化权限逻辑：提交审批 (状态设为 DONE) 必须由项目负责人执行 ---
                if new_status == 'DONE' and node.project.approval_workflow:
                    # 检查是否为项目负责人或超级管理员
                    if not (request.user == node.project.manager or request.user.is_superuser):
                        # 如果不是负责人，不允许提交审批，返回错误提示
                        form.add_error('status', "只有项目负责人有权提交审批。")
                        return render(request, self.template_name, {
                            'node': node,
                            'form': form,
                        })

                    # --- 上下文数据，供流程图条件表达式使用 ---
                    user = request.user

                    context_data = {
                        'project_name': node.project.name,
                        'node_stage': node.get_stage_display(),
                        'applicant_username': user.username,
                        'department_name': user.department.name if user.department else "未知部门",
                    }

                    # 启动审批流程
                    callback_config = {
                        'handler': 'app_project.workflow_handlers.handle_project_node_workflow_callback',
                        'args': {
                            'node_pk': node.pk,
                        }
                    }

                    instance = WorkflowEngine.start_instance(
                        definition=node.project.approval_workflow,
                        started_by=request.user,
                        related_object=node,
                        context_data=context_data,
                        callback_config=callback_config
                    )
                    # 将节点状态设为待审批，并关联流程实例
                    node.status = 'AWAITING_APPROVAL'
                    node.workflow_instance = instance
                    node.remark = form.cleaned_data.get('remark')
                    node.save()
                    return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

                # 常规保存 (协同成员可以更新 DOING, PAUSED 等状态，但不能提交 DONE)
                form.save()
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return render(request, self.template_name, {
            'node': node,
            'form': form,
        })


# ==========================================
# 5. 节点操作：申报不合格 (失败重开)
# ==========================================
class NodeFailedView(ProjectAccessMixin, View):
    """节点失败：需有 change_project 权限"""
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_progress_failed.html'

    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_object_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_object_permission(node.project)

        remark = request.POST.get('remark', '测试不通过，需返工')
        node.perform_failure_logic(remark)

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})


# ==========================================
# 6. 节点操作：客户干预/反馈
# ==========================================
class InsertFeedbackView(ProjectAccessMixin, View):
    """客户反馈：需有 change_project 权限"""
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_progress_feedback.html'

    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_object_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        current_node = get_object_or_404(ProjectNode, pk=pk)
        self.check_object_permission(current_node.project)

        current_node.project.handle_customer_feedback(
            current_node=current_node,
            feedback_type=request.POST.get('feedback_type'),
            content=request.POST.get('remark')
        )

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
