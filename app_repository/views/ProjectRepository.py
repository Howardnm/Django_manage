from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, UpdateView, CreateView, DetailView
from django.db.models import Q
from django.contrib.auth import get_user_model
from app_repository.forms import ProjectRepositoryForm
from app_repository.utils.filters import ProjectRepositoryFilter
from app_project.models import Project
from app_repository.models import ProjectRepository, Customer, OEM
from app_repository.mixins import RepositoryAccessMixin
from app_material.models.material import ApplicationScenario, MaterialCharacteristic

User = get_user_model()


class ProjectRepositoryUpdateView(RepositoryAccessMixin, UpdateView):
    """档案更新：需有 change_projectrepository 权限，且仅限本部门。"""
    permission_required = 'app_repository.change_projectrepository'
    model = ProjectRepository
    form_class = ProjectRepositoryForm
    template_name = 'apps/app_repository/project_repo/project_repo_form.html'

    def get_object(self, queryset=None):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, pk=project_id)

        # 仅获取已有档案，不自动创建。避免在权限校验前生成孤立数据库记录。
        repo = get_object_or_404(ProjectRepository, project=project)

        # 核心安全校验：拦截跨部门编辑
        self.check_object_permission(repo)
        return repo

    def form_valid(self, form):
        messages.success(self.request, "项目档案基础信息已更新")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.project.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.object.project
        return context


class ProjectFileDetailView(RepositoryAccessMixin, DetailView):
    """项目资料库详情页 — 按项目节点分组展示附件"""
    permission_required = 'app_repository.view_projectrepository'
    model = ProjectRepository
    template_name = 'apps/app_repository/project_repo/project_file_detail.html'
    context_object_name = 'repo'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.object.project

        # 从 Attachment 表查询该 repo 的所有附件
        from django.contrib.contenttypes.models import ContentType
        from app_attachment.models import Attachment
        ct = ContentType.objects.get_for_model(ProjectRepository)
        attachments = Attachment.objects.filter(
            content_type=ct, object_id=self.object.pk, is_deleted=False,
        ).order_by('-uploaded_at')

        # 按 group_key 分组（保持节点顺序）
        nodes = list(project.nodes.all().order_by('order'))
        node_map = {f"node:{n.pk}": n for n in nodes}
        # 预初始化所有节点分组（空文件列表），保证卡片顺序 = 节点顺序
        node_index = {n.pk: i for i, n in enumerate(nodes)}
        grouped_files = [{'node': n, 'files': []} for n in nodes]
        general_files = []

        for att in attachments:
            if att.group_key and att.group_key in node_map:
                node = node_map[att.group_key]
                idx = node_index[node.pk]
                grouped_files[idx]['files'].append(att)
            else:
                general_files.append(att)

        # 过滤掉空分组（没有附件的节点不显示）
        grouped_files = [g for g in grouped_files if g['files']]

        # 使用项目模型已有的 current_active_node 方法
        active_node = project.current_active_node
        active_node_id = f"node:{active_node.pk}" if active_node else ''

        context.update({
            'project': project,
            'grouped_files': grouped_files,
            'general_files': general_files,
            'ct_id': ct.id,
            'active_node_id': active_node_id,
        })
        return context


class RepoAutocompleteView(RepositoryAccessMixin, View):
    """搜索接口：跨组搜索以便指派任务。"""
    permission_required = 'app_repository.view_projectrepository'

    def get(self, request):
        model_type = request.GET.get('model')
        query = request.GET.get('q', '')
        data = []

        if model_type == 'customer':
            qs = Customer.objects.filter(company_name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.company_name} for item in qs]
        elif model_type == 'oem':
            qs = OEM.objects.filter(Q(name__icontains=query) | Q(short_name__icontains=query))[:20]
            data = [{'value': item.pk, 'text': f"{item.name} ({item.short_name})" if item.short_name else item.name} for item in qs]
        elif model_type == 'salesperson':
            qs = User.objects.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query),
                is_staff=True
            )[:20]
            data = [{'value': item.pk, 'text': item.get_full_name() or item.username} for item in qs]
        elif model_type == 'scenario':
            qs = ApplicationScenario.objects.filter(name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.name} for item in qs]
        elif model_type == 'characteristic':
            qs = MaterialCharacteristic.objects.filter(name__icontains=query)[:20]
            data = [{'value': item.pk, 'text': item.name} for item in qs]

        return JsonResponse(data, safe=False)
