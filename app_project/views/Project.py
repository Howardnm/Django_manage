import json

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, UpdateView, DetailView

from app_project.forms import ProjectForm
from app_project.mixins import ProjectAccessMixin
from django.db.models import Prefetch
from app_project.models import Project, ProjectConfig, ProjectNode, ProjectMember, ProjectSalesMember, ProjectFieldChange
from app_repository.models import ProjectRepositoryFieldChange
from app_project.utils.calculate_project_gantt import get_project_gantt_data
from app_project.utils.filters import ProjectFilter
from app_workflow.services import WorkflowService


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

        # 自动生成项目编码（如果未填写）
        if not form.instance.code:
            from django.utils import timezone
            today = timezone.localdate()
            date_prefix = today.strftime('%Y%m%d')
            # 统计当天已创建的项目数，用于生成序号
            count_today = Project.objects.filter(
                created_at__date=today
            ).count() + 1
            form.instance.code = f'PRJ-{date_prefix}-{count_today:03d}'

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
    - 审批：若配置了 default_project_edit_approval_workflow，编辑提交后进入审批流程，
      审批通过后才更新 Project 字段。未配置则直接保存。
    """
    permission_required = 'app_project.change_project'
    model = Project
    form_class = ProjectForm
    template_name = 'apps/app_project/project_form.html'

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

    def get_success_url(self):
        return reverse('project_detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        config = ProjectConfig.get()
        context['project_edit_workflow_configured'] = bool(
            config.default_project_edit_approval_workflow_id
        )
        return context

    def form_valid(self, form):
        self.check_edit_permission(self.object)
        project = self.object
        config = ProjectConfig.get()
        edit_workflow = config.default_project_edit_approval_workflow

        # 防御：清除已失效的 workflow_instance 引用（回调异常时可能残留）
        if project.workflow_instance_id and project.workflow_instance.status != 'RUNNING':
            project.workflow_instance = None
            project.save(update_fields=['workflow_instance'])

        # 无审批流程配置 → 直接保存（向后兼容）
        if not edit_workflow:
            form.save()
            messages.success(self.request, "项目信息已更新")
            return redirect(self.get_success_url())

        # 检查是否已有进行中的审批（双重校验）
        if project.workflow_instance_id or ProjectFieldChange.objects.filter(
            project=project, status='PENDING'
        ).exists():
            messages.warning(self.request, "已有待审批的项目信息变更，请等待审批完成后再提交")
            return redirect(self.get_success_url())

        # 创建变更记录 — Project 原值保持不变，等待审批
        change = ProjectFieldChange.objects.create(
            project=project,
            code=form.cleaned_data.get('code', ''),
            name=form.cleaned_data.get('name', ''),
            grade=form.cleaned_data.get('grade'),
            material=form.cleaned_data.get('material'),
            description=form.cleaned_data.get('description', ''),
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
            'handler': 'app_project.workflow_handlers.handle_project_change_callback',
            'args': {'change_id': change.pk},
        }

        instance = WorkflowService.start(
            definition=edit_workflow,
            started_by=user,
            related_object=change,
            context_data=context_data,
            callback_config=callback_config,
        )

        change.workflow_instance = instance
        change.save(update_fields=['workflow_instance'])

        project.workflow_instance = instance
        project.save(update_fields=['workflow_instance'])

        messages.success(self.request, "项目信息变更已提交审批，请等待审批结果")
        return redirect(self.get_success_url())


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
        'manager',
        'grade',
        'workflow_instance',
        'repository', 'repository__customer', 'repository__oem',
        'repository__salesperson', 'repository__workflow_instance__started_by',
        'material', 'material__category',
    ).prefetch_related(
        # 阶段节点 — 同时预取关联的审批实例、不合格原因、客户意见类型
        Prefetch('nodes', queryset=ProjectNode.objects.select_related(
            'workflow_instance', 'failure_reason', 'feedback_type',
        )),
        # 协同成员 + 销售成员 — 避免模板中 N+1 查询 user FK
        Prefetch('members', queryset=ProjectMember.objects.select_related('user')),
        Prefetch('sales_members', queryset=ProjectSalesMember.objects.select_related('user')),
        # 变更记录 — 预取提交人
        Prefetch('field_changes', queryset=ProjectFieldChange.objects.select_related('submitted_by')),
        # 项目档案的变更记录 — 通过 repository FK 穿透预取
        Prefetch('repository__field_changes',
                  queryset=ProjectRepositoryFieldChange.objects.select_related('submitted_by')),
        'material__scenarios',
        'material__characteristics',
    )

    def get_object(self, queryset=None):
        return self.get_object_or_deny()

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
            'field_changes': project.field_changes.all()[:5],
            'user_can_manage_content': project.user_can_manage_content(self.request.user),
        })
        return context


class ProjectFieldChangeDetailView(ProjectAccessMixin, View):
    """项目信息变更记录详情模态框"""
    permission_required = 'app_project.view_project'
    template_name = 'apps/app_project/modal/_field_change_detail.html'

    def get(self, request, pk):
        change = get_object_or_404(
            ProjectFieldChange.objects.select_related(
                'project', 'submitted_by', 'grade', 'material',
            ),
            pk=pk,
        )
        self.check_object_permission(change.project)
        return render(request, self.template_name, {'change': change})


