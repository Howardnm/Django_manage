import json

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView, DetailView

from app_project.forms import ProjectForm
from app_project.mixins import ProjectAccessMixin
from app_project.models import Project, ProjectConfig, ProjectNode
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
        projects_qs = Project.objects.select_related(
            'manager',
            'repository',
            'repository__customer',
            'repository__oem',
            'material'
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
        config = ProjectConfig.get()
        if config.default_approval_workflow_id:
            form.instance.approval_workflow = config.default_approval_workflow
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})


class ProjectUpdateView(ProjectAccessMixin, UpdateView):
    """
    项目编辑：
    - 准入：需有 change_project 权限。
    """
    permission_required = 'app_project.change_project'
    model = Project
    form_class = ProjectForm
    template_name = 'apps/app_project/project_form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # 核心修复：更正方法名
        self.check_object_permission(obj)
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
        'repository__salesperson', 'material', 'material__category',
    ).prefetch_related(
        'nodes', 'material__scenarios'
    )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # 核心修复：保持方法名一致
        self.check_object_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object
        repo = getattr(project, 'repository', None)

        # 表单提交计数
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Count
        from app_form_management.models import FormSubmission

        project_ct = ContentType.objects.get_for_model(Project)
        node_ct = ContentType.objects.get_for_model(ProjectNode)

        project_form_count = FormSubmission.objects.filter(
            content_type=project_ct, object_id=project.pk
        ).count()

        node_ids = list(project.nodes.values_list('pk', flat=True))
        node_count_pairs = (
            FormSubmission.objects
            .filter(content_type=node_ct, object_id__in=node_ids)
            .values_list('object_id')
            .annotate(cnt=Count('id'))
            .values_list('object_id', 'cnt')
        ) if node_ids else []
        node_form_counts = dict(node_count_pairs)

        nodes = project.cached_nodes
        for node in nodes:
            node.form_count = node_form_counts.get(node.pk, 0)

        # 附件上传所需的 ContentType ID
        from app_repository.models import ProjectRepository
        repo_ct_id = ContentType.objects.get_for_model(ProjectRepository).id if repo else None

        context.update({
            'nodes': nodes,
            'repo': repo,
            'repo_ct_id': repo_ct_id,
            'material': project.material,
            'gantt_data_json': get_project_gantt_data(project),
            'project_form_count': project_form_count,
            'total_form_count': project_form_count + sum(node_form_counts.values()),
        })
        return context


# ==========================================
# 4. 项目全局配置（仅超级管理员）
# ==========================================
class ProjectConfigView(ProjectAccessMixin, View):
    """项目全局配置：设置默认审批流程等。仅超级管理员可访问。"""

    def get(self, request):
        if not request.user.is_superuser:
            messages.error(request, "您的账号权限不足，无法访问该页面。")
            return redirect(getattr(settings, 'PERM_DENIED_URL', 'panel_home'))

        from app_workflow.models import WorkflowDefinition
        config = ProjectConfig.get()
        workflows = WorkflowDefinition.objects.filter(is_active=True).order_by('name')
        return render(request, 'apps/app_project/config.html', {
            'config': config,
            'workflows': workflows,
        })

    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可修改项目配置。'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        config = ProjectConfig.get()
        config.default_approval_workflow_id = data.get('workflow_id') or None
        config.save()
        return JsonResponse({'status': 'success'})
