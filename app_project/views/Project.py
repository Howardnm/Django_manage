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
        # 1. 基础查询集深度优化
        # 【优化】利用冗余字段后，列表页不再需要 prefetch_related('nodes')
        # 也不再 defer('description')，因为我们可以在列表页显示项目描述
        base_qs = Project.objects.select_related(
            'manager',
            'repository',
            'repository__customer',
            'repository__oem',
            'repository__material'
        ).order_by('-created_at')

        # 2. 权限过滤 (你的 Mixin)
        projects_qs = self.get_permitted_queryset(base_qs)

        # 3. 接入 Filter
        filter_set = ProjectFilter(request.GET, queryset=projects_qs, request=request)
        queryset = filter_set.qs

        # 4. 分页
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
        # 【修改】创建成功后，跳转到该项目的详情页
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
class ProjectDetailView(LoginRequiredMixin, ProjectPermissionMixin, DetailView):
    model = Project
    template_name = 'apps/app_project/detail.html'
    context_object_name = 'project'

    # 详情页依然需要加载所有节点信息，保持不变
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
        'repository__material__scenarios',  # 多对多必须用 prefetch
        'repository__material__additional_files'
    )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_project_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object

        context.update({
            'nodes': project.cached_nodes,
            'repo': getattr(project, 'repository', None),
            'gantt_data_json': get_project_gantt_data(project)
        })
        return context
