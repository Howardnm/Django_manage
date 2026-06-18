from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.http import HttpResponse

from app_project.models import Project, ProjectSalesMember
from app_project.forms import ProjectSalesMemberForm
from app_project.mixins import ProjectAccessMixin


class ProjectSalesMemberManageView(ProjectAccessMixin, View):
    permission_required = 'app_project.change_project'
    template_name = 'apps/app_project/detail/modal_box/_project_sales_member_form.html'

    def get_project_and_check_perm(self, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_object_permission(project)
        return project

    def get(self, request, pk):
        project = self.get_project_and_check_perm(pk)

        member_id = request.GET.get('member_id')
        if member_id:
            member = get_object_or_404(ProjectSalesMember, pk=member_id, project=project)
            form = ProjectSalesMemberForm(instance=member, project=project)
        else:
            form = ProjectSalesMemberForm(project=project)

        return render(request, self.template_name, {
            'project': project,
            'form': form,
            'member_id': member_id
        })

    def post(self, request, pk):
        project = self.get_project_and_check_perm(pk)

        member_id = request.POST.get('member_id')
        if member_id:
            member = get_object_or_404(ProjectSalesMember, pk=member_id, project=project)
            form = ProjectSalesMemberForm(request.POST, instance=member, project=project)
        else:
            form = ProjectSalesMemberForm(request.POST, project=project)

        if form.is_valid():
            form.instance.project = project
            form.save()
            return HttpResponse(status=204, headers={'HX-Refresh': 'true'})

        return render(request, self.template_name, {
            'project': project,
            'form': form,
            'member_id': member_id
        })


class ProjectSalesMemberDeleteView(ProjectAccessMixin, View):
    permission_required = 'app_project.change_project'

    def post(self, request, pk):
        member = get_object_or_404(ProjectSalesMember.objects.select_related('project'), pk=pk)
        self.check_object_permission(member.project)
        project_id = member.project.id

        member.delete()
        messages.success(request, "销售成员已从项目组移除")
        return redirect(reverse('project_detail', kwargs={'pk': project_id}))
