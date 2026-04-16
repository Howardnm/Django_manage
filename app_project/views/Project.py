from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView, DetailView

from app_project.forms import ProjectForm
from app_project.mixins import ProjectPermissionMixin
from app_project.models import Project
from app_project.utils.calculate_project_gantt import get_project_gantt_data
from app_project.utils.filters import ProjectFilter


# ==========================================
# 1. 项目列表 (查询与展示)
# ==========================================
class ProjectListView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, View):
    permission_required = 'app_project.view_project'

    def get(self, request):
        base_qs = Project.objects.select_related(
            'manager',
            'repository',
            'repository__customer',
            'repository__oem',
            'repository__material'
        ).order_by('-created_at')

        projects_qs = self.get_permitted_queryset(base_qs)
        filter_set = ProjectFilter(request.GET, queryset=projects_qs, request=request)
        queryset = filter_set.qs
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        context = {
            'page_obj': page_obj,
            'filter': filter_set,
            'current_sort': request.GET.get('sort', ''),
        }
        return render(request, 'apps/app_project/list.html', context)


class ProjectCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_project.add_project'
    raise_exception = True
    model = Project
    form_class = ProjectForm
    template_name = 'apps/app_project/project_form.html'

    def form_valid(self, form):
        form.instance.manager = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})


class ProjectUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_project.change_project'
    raise_exception = True
    model = Project
    form_class = ProjectForm
    template_name = 'apps/app_project/project_form.html'

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 3. 项目详情
# ==========================================
class ProjectDetailView(LoginRequiredMixin, PermissionRequiredMixin, ProjectPermissionMixin, DetailView):
    permission_required = 'app_project.view_project'
    model = Project
    template_name = 'apps/app_project/detail.html'
    context_object_name = 'project'

    queryset = Project.objects.select_related(
        'manager',
        'repository',
        'repository__customer',
        'repository__oem',
        'repository__salesperson',
        'repository__material',
        'repository__material__category',
    ).prefetch_related(
        'nodes',
        'repository__files',
        'repository__material__scenarios',
        'repository__material__additional_files'
    )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_project_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object

        # 核心修复：确保 context 中同时包含 repo 变量
        project_repo = getattr(project, 'repository', None)
        material = project_repo.material if project_repo else None

        context.update({
            'nodes': project.cached_nodes,
            'project_repo': project_repo, 
            'repo': project_repo,         # 增加 repo 别名以兼容模板
            'material': material,
            'gantt_data_json': get_project_gantt_data(project)
        })
        return context
