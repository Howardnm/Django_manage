from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.http import HttpResponse

from app_project.models import Project, ProjectMember
from app_project.forms import ProjectMemberForm
from app_project.mixins import ProjectPermissionMixin


# ==========================================
# 7. 项目成员协作管理 (协作绩效功能)
# ==========================================

class ProjectMemberManageView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    """
    项目成员管理视图 (添加/编辑成员)
    """
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_member_form.html'

    def get_project_and_check_perm(self, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_project_permission(project)
        return project

    def get(self, request, pk):
        project = self.get_project_and_check_perm(pk)
        
        # 处理编辑
        member_id = request.GET.get('member_id')
        if member_id:
            member = get_object_or_404(ProjectMember, pk=member_id, project=project)
            form = ProjectMemberForm(instance=member, project=project)
        else:
            form = ProjectMemberForm(project=project)

        return render(request, self.template_name, {
            'project': project,
            'form': form,
            'member_id': member_id
        })

    def post(self, request, pk):
        project = self.get_project_and_check_perm(pk)
        
        # 处理编辑
        member_id = request.POST.get('member_id')
        if member_id:
            member = get_object_or_404(ProjectMember, pk=member_id, project=project)
            form = ProjectMemberForm(request.POST, instance=member, project=project)
        else:
            form = ProjectMemberForm(request.POST, project=project)

        if form.is_valid():
            form.instance.project = project
            form.save()
            # 成功保存，返回 204 并刷新页面
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        # 【核心修复】验证失败，重新渲染模态框内容，确保错误信息通过 HTMX 塞回模态框
        return render(request, self.template_name, {
            'project': project,
            'form': form,
            'member_id': member_id
        })


class ProjectMemberDeleteView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    """
    项目成员移除视图
    """
    permission_required = 'app_project.change_project'

    def post(self, request, pk):
        member = get_object_or_404(ProjectMember, pk=pk)
        project_id = member.project.id
        self.check_project_permission(member.project)
        
        member.delete()
        messages.success(request, "成员已从项目组移除")
        return redirect(reverse('project_detail', kwargs={'pk': project_id}))
