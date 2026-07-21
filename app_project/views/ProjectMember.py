from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.http import HttpResponse

from app_project.models import Project, ProjectMember
from app_project.forms import ProjectMemberForm
from app_project.mixins import ProjectAccessMixin


# ==========================================
# 7. 项目成员协作管理 (协作绩效功能)
# ==========================================

class ProjectMemberManageView(ProjectAccessMixin, View):
    """项目成员管理：需有 change_project 权限"""
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/modal/_member_form.html'

    def get_project_and_check_perm(self, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_object_permission(project)
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

        existing_sum = sum(
            float(m.workload_share) for m in project.members.all()
            if str(m.id) != member_id
        )

        return render(request, self.template_name, {
            'project': project,
            'form': form,
            'member_id': member_id,
            'existing_sum': existing_sum,
        })

    def post(self, request, pk):
        project = self.get_project_and_check_perm(pk)
        self.check_edit_permission(project)

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
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        existing_sum = sum(
            float(m.workload_share) for m in project.members.all()
            if str(m.id) != member_id
        )

        return render(request, self.template_name, {
            'project': project,
            'form': form,
            'member_id': member_id,
            'existing_sum': existing_sum,
        })


class ProjectMemberDeleteView(ProjectAccessMixin, View):
    """成员移除：需有 change_project 权限"""
    permission_required = 'app_project.change_project'

    def post(self, request, pk):
        member = get_object_or_404(ProjectMember.objects.select_related('project'), pk=pk)
        self.check_object_permission(member.project)
        self.check_edit_permission(member.project)
        project_id = member.project.id

        member.delete()
        messages.success(request, "成员已从项目组移除")
        return redirect(reverse('project_detail', kwargs={'pk': project_id}))
