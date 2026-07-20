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
from app_repository.models import ProjectRepository, ProjectRepositoryFieldChange, Customer, OEM
from app_repository.mixins import RepositoryAccessMixin
from app_material.models.material import ApplicationScenario, MaterialCharacteristic
from app_workflow.services import WorkflowService

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
        repo = self.object
        project = repo.project

        # 读取档案审批流程配置
        from app_project.models import ProjectConfig
        repo_workflow = ProjectConfig.get().default_repository_approval_workflow

        # 防御：清除已失效的 workflow_instance 引用（回调异常时可能残留）
        if repo.workflow_instance_id and repo.workflow_instance.status != 'RUNNING':
            repo.workflow_instance = None
            repo.save(update_fields=['workflow_instance'])

        # 无审批流程配置 → 直接保存
        if not repo_workflow:
            form.save()
            messages.success(self.request, "项目档案已更新")
            return redirect(self.get_success_url())

        # 检查是否已有进行中的审批（双重校验）
        if repo.workflow_instance_id or ProjectRepositoryFieldChange.objects.filter(
            repository=repo, status='PENDING'
        ).exists():
            messages.warning(self.request, "已有待审批的档案变更，请等待审批完成后再提交")
            return redirect(self.get_success_url())

        # 创建全字段变更记录 — Repository 原值保持不变，等待审批
        change = ProjectRepositoryFieldChange.objects.create(
            repository=repo,
            customer=form.cleaned_data.get('customer'),
            oem=form.cleaned_data.get('oem'),
            salesperson=form.cleaned_data.get('salesperson'),
            product_name=form.cleaned_data.get('product_name', ''),
            product_code=form.cleaned_data.get('product_code', ''),
            target_cost=form.cleaned_data.get('target_cost'),
            competitor_price=form.cleaned_data.get('competitor_price'),
            estimated_order_volume=form.cleaned_data.get('estimated_order_volume'),
            submitted_by=self.request.user,
            submission_comment=form.cleaned_data.get('submission_comment', ''),
        )

        # 启动审批流程
        user = self.request.user
        context_data = {
            'change_id': change.pk,
            'project_name': project.name,
            'submission_comment': change.submission_comment,
            'submitted_by': user.username,
            'applicant_username': user.username,
            'department_name': user.department.name if user.department else "未知部门",
        }

        callback_config = {
            'handler': 'app_repository.workflow_handlers.handle_repo_change_callback',
            'args': {'change_id': change.pk},
        }

        instance = WorkflowService.start(
            definition=repo_workflow,
            started_by=user,
            related_object=change,
            context_data=context_data,
            callback_config=callback_config,
        )

        change.workflow_instance = instance
        change.save(update_fields=['workflow_instance'])

        repo.workflow_instance = instance
        repo.save(update_fields=['workflow_instance'])

        messages.success(self.request, "档案变更已提交审批，请等待审批结果")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.project.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['project'] = self.object.project
        context['repo'] = self.object
        from app_project.models import ProjectConfig
        context['repo_workflow_configured'] = bool(
            ProjectConfig.get().default_repository_approval_workflow_id
        )
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


class RepoFieldChangeModalView(RepositoryAccessMixin, View):
    """变更记录详情模态框"""
    permission_required = 'app_repository.view_projectrepository'
    template_name = 'apps/app_repository/modal/_field_change_detail.html'

    def get(self, request, pk):
        change = get_object_or_404(
            ProjectRepositoryFieldChange.objects.select_related(
                'repository__project', 'submitted_by',
                'customer', 'oem', 'salesperson',
            ),
            pk=pk
        )
        self.check_object_permission(change.repository)
        return render(request, self.template_name, {'change': change})


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
