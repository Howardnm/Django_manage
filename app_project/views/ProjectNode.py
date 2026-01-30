from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from app_project.forms import ProjectNodeUpdateForm
from app_project.mixins import ProjectPermissionMixin
from app_project.models import ProjectNode


# ==========================================
# 4. 节点操作：常规更新
# ==========================================
class ProjectNodeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_progress_update.html'

    def get_node_and_check_perm(self, pk):
        """辅助方法：获取节点并检查权限"""
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)
        return node

    def get(self, request, pk):
        node = self.get_node_and_check_perm(pk)
        return render(request, self.template_name, {
            'node': node,
            'status_choices': ProjectNode.STATUS_CHOICES
        })

    def post(self, request, pk):
        node = self.get_node_and_check_perm(pk)
        form = ProjectNodeUpdateForm(request.POST, instance=node)

        if form.is_valid():
            form.save()
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return render(request, self.template_name, {
            'node': node,
            'status_choices': ProjectNode.STATUS_CHOICES,
            'form': form
        })


# ==========================================
# 5. 节点操作：申报不合格 (失败重开)
# ==========================================
class NodeFailedView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_progress_failed.html'

    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)  # 【安全】

        remark = request.POST.get('remark', '测试不通过，需返工')

        # 业务逻辑已下沉到 Model
        node.perform_failure_logic(remark)

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})


# ==========================================
# 6. 节点操作：客户干预/反馈
# ==========================================
class InsertFeedbackView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_progress_feedback.html'

    def get(self, request, pk):
        node = get_object_or_404(ProjectNode, pk=pk)
        self.check_project_permission(node.project)
        return render(request, self.template_name, {'node': node})

    def post(self, request, pk):
        current_node = get_object_or_404(ProjectNode, pk=pk)

        # 权限检查 (假设你用了 Mixin)
        self.check_project_permission(current_node.project)

        # 核心逻辑：直接调用 Model 方法
        current_node.project.handle_customer_feedback(
            current_node=current_node,
            feedback_type=request.POST.get('feedback_type'),
            content=request.POST.get('remark')
        )

        return HttpResponse(status=204, headers={'HX-Refresh': 'true'})
