from django.core.paginator import Paginator
from django.shortcuts import render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView, DetailView

from app_project.forms import ProjectForm
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project
from app_project.utils.calculate_project_gantt import get_project_gantt_data
from app_project.utils.filters import ProjectFilter


# ==========================================
# 1. 项目列表
# ==========================================
class ProjectListView(ProjectAccessMixin, View):
    """
    项目列表：
    - 准入：需有 app_project.view_project 权限。
    - 隔离：仅限部门内项目 + 参与成员项目。
    """
    permission_required = 'app_project.view_project'

    def get(self, request):
        # 这里的 super().get_queryset() 已被 ProjectAccessMixin 过滤
        projects_qs = Project.objects.select_related(
            'manager',
            'repository',
            'repository__customer',
            'repository__oem',
            'repository__material'
        ).order_by('-created_at')

        # 应用 Mixin 中定义的过滤逻辑
        projects_qs = self.get_permitted_queryset(projects_qs)
        
        filter_set = ProjectFilter(request.GET, queryset=projects_qs, request=request)
        queryset = filter_set.qs
        paginator = Paginator(queryset, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        return render(request, 'apps/app_project/list.html', {
            'page_obj': page_obj,
            'filter': filter_set,
            'current_sort': request.GET.get('sort', ''),
        })

    def get_permitted_queryset(self, qs):
        """兼容 View 模式下的过滤调用"""
        self.queryset = qs
        return self.get_queryset()


# ==========================================
# 2. 项目创建/编辑
# ==========================================
class ProjectCreateView(ProjectAccessMixin, CreateView):
    """
    项目创建：需有 add_project 权限。
    """
    permission_required = 'app_project.add_project'
    model = Project
    form_class = ProjectForm
    template_name = 'apps/app_project/project_form.html'

    def form_valid(self, form):
        form.instance.manager = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})


class ProjectUpdateView(ProjectAccessMixin, UpdateView):
    """
    项目编辑：
    - 准入：需有 change_project 权限。
    - 细分：默认继承 min_level_required=1。
    - 若需限制特定项目 11 级，只需在子类中重写属性。
    """
    permission_required = 'app_project.change_project'
    model = Project
    form_class = ProjectForm
    template_name = 'apps/app_project/project_form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_object_level_permission(obj)
        return obj

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})


# ==========================================
# 3. 项目详情
# ==========================================
class ProjectDetailView(ProjectAccessMixin, DetailView):
    """
    项目详情：需有 view_project 权限。
    """
    permission_required = 'app_project.view_project'
    model = Project
    template_name = 'apps/app_project/detail.html'
    context_object_name = 'project'

    queryset = Project.objects.select_related(
        'manager', 'repository', 'repository__customer', 'repository__oem',
        'repository__salesperson', 'repository__material', 'repository__material__category',
    ).prefetch_related(
        'nodes', 'repository__files', 'repository__material__scenarios',
        'repository__material__additional_files'
    )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_object_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        repo = getattr(project, 'repository', None)

        context.update({
            'nodes': project.cached_nodes,
            'repo': repo,
            'material': repo.material if repo else None,
            'gantt_data_json': get_project_gantt_data(project)
        })
        return context
