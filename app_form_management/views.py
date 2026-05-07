import json
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.http import JsonResponse
from django.contrib import messages
from django.http import Http404
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator

from .models import FormTemplate, FormSubmission
from app_workflow.models import WorkflowDefinition
from app_project.models import Project, ProjectNode
from app_project.mixins import ProjectAccessMixin
from .mixins import FormManagementAccessMixin
from .services import submission_service
from .registry import get_target, get_module_choices, search_entities
from .filters import FormTemplateFilter, MyDraftsFilter, MySubmissionsFilter


# ==========================================
# 1. 表单模板管理
# ==========================================

class FormTemplateListView(FormManagementAccessMixin, View):
    def get(self, request):
        qs = FormTemplate.objects.all().select_related('created_by', 'workflow')
        filter_set = FormTemplateFilter(request.GET, queryset=qs)
        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))
        workflows = WorkflowDefinition.objects.filter(is_active=True)
        return render(request, 'apps/app_form_management/template_list.html', {
            'page_obj': page_obj,
            'filter': filter_set,
            'workflows': workflows,
        })


class FormTemplateCreateView(FormManagementAccessMixin, View):
    def get(self, request):
        workflows = WorkflowDefinition.objects.filter(is_active=True)
        return render(request, 'apps/app_form_management/template_create.html', {
            'template': None,
            'workflows': workflows,
            'form_config_json': '[]',
            'form_option_json': '{}',
        })

    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可创建表单模板。'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'status': 'error', 'message': '表单名称不能为空。'}, status=400)

        template = FormTemplate.objects.create(
            name=name,
            description=data.get('description', ''),
            is_active=data.get('is_active', True),
            form_config=data.get('form_config', []),
            form_option=data.get('form_option', {}),
            workflow_id=data.get('workflow_id') or None,
            created_by=request.user,
        )
        return JsonResponse({'status': 'success', 'pk': template.pk})


class FormTemplateUpdateView(FormManagementAccessMixin, View):
    def get(self, request, pk):
        if not request.user.is_superuser:
            messages.error(request, '仅超级管理员可编辑表单模板。')
            return redirect('form_template_list')

        template = get_object_or_404(FormTemplate, pk=pk)
        workflows = WorkflowDefinition.objects.filter(is_active=True)
        return render(request, 'apps/app_form_management/template_create.html', {
            'template': template,
            'workflows': workflows,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
        })

    def post(self, request, pk):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可编辑表单模板。'}, status=403)

        template = get_object_or_404(FormTemplate, pk=pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'status': 'error', 'message': '表单名称不能为空。'}, status=400)

        template.name = name
        template.description = data.get('description', '')
        template.is_active = data.get('is_active', True)
        template.form_config = data.get('form_config', [])
        template.form_option = data.get('form_option', {})
        template.workflow_id = data.get('workflow_id') or None
        template.save()
        return JsonResponse({'status': 'success', 'pk': template.pk})


class FormTemplateBasicInfoUpdateView(FormManagementAccessMixin, View):
    def post(self, request, pk):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可修改表单基本信息。'}, status=403)

        template = get_object_or_404(FormTemplate, pk=pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        name = data.get('name', '').strip()
        if name:
            template.name = name
        template.description = data.get('description', '')
        template.is_active = data.get('is_active', True)
        template.workflow_id = data.get('workflow_id') or None
        template.save()
        return JsonResponse({'status': 'success'})


class FormTemplateDeleteView(FormManagementAccessMixin, View):
    def post(self, request, pk):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可删除表单模板。'}, status=403)

        template = get_object_or_404(FormTemplate, pk=pk)
        template.delete()
        return JsonResponse({'status': 'success'})


class FormTemplateDetailView(FormManagementAccessMixin, View):
    def get(self, request, pk):
        template = get_object_or_404(FormTemplate, pk=pk)
        return render(request, 'apps/app_form_management/template_detail.html', {
            'template': template,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
        })


# ==========================================
# 2. 表单填写与提交
# ==========================================

class FormSubmissionCreateView(FormManagementAccessMixin, View):
    def _resolve_target(self, target_alias=None, object_id=None):
        """通过白名单别名解析目标对象。不在 registry 中的 alias 直接 404。"""
        if target_alias and object_id:
            target_model = get_target(target_alias)
            if target_model is None:
                raise Http404
            return get_object_or_404(target_model, pk=object_id)
        return None

    def _get_target_display(self, target):
        """Build a human-readable label for the target object."""
        if target is None:
            return None
        model_name = target._meta.verbose_name
        if hasattr(target, 'name'):
            return f'{model_name}：{target.name}'
        return f'{model_name} #{target.pk}'

    def get(self, request, template_pk, target_alias=None, obj_pk=None):
        template = get_object_or_404(FormTemplate, pk=template_pk)
        target = self._resolve_target(target_alias=target_alias, object_id=obj_pk)

        existing = None
        submit_url = reverse('form_submission_fill', kwargs={'template_pk': template_pk})
        if target:
            existing = submission_service.get_draft(template, target, request.user)
            if target_alias and obj_pk:
                submit_url = reverse('form_submission_fill_target', kwargs={
                    'template_pk': template_pk,
                    'target_alias': target_alias,
                    'obj_pk': obj_pk,
                })
        else:
            existing = FormSubmission.objects.filter(
                template=template, submitted_by=request.user, status='DRAFT'
            ).first()

        return render(request, 'apps/app_form_management/submission_fill.html', {
            'template': template,
            'target': target,
            'target_display': self._get_target_display(target),
            'existing': existing,
            'submit_url': submit_url,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
            'existing_data_json': json.dumps(existing.form_data, ensure_ascii=False) if existing else '{}',
        })

    def post(self, request, template_pk, target_alias=None, obj_pk=None):
        template = get_object_or_404(FormTemplate, pk=template_pk)
        target = self._resolve_target(target_alias=target_alias, object_id=obj_pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        form_data = data.get('form_data', {})
        status = data.get('status', 'SUBMITTED')
        remark = data.get('remark', '')

        if target:
            submission = submission_service.create_or_update(
                template=template,
                target_object=target,
                submitted_by=request.user,
                form_data=form_data,
                status=status,
                remark=remark,
            )
        else:
            submission = FormSubmission.objects.filter(
                template=template, submitted_by=request.user, status='DRAFT'
            ).first()
            if submission:
                submission.form_data = form_data
                submission.remark = remark
                submission.status = status
                submission.save()
            else:
                submission = FormSubmission.objects.create(
                    template=template,
                    submitted_by=request.user,
                    form_data=form_data,
                    status=status,
                    remark=remark,
                )

        # 提交时如果模板关联了审批流程，自动启动流程实例
        if status == 'SUBMITTED' and template.workflow_id and not submission.workflow_instance_id:
            from app_workflow.utils import WorkflowEngine
            try:
                instance = WorkflowEngine.start_instance(
                    definition=template.workflow,
                    started_by=request.user,
                    related_object=submission,
                    context_data={'form_data': form_data, 'remark': remark},
                )
                submission.workflow_instance = instance
                submission.save(update_fields=['workflow_instance'])
            except Exception:
                pass  # 流程启动失败不阻塞表单提交

        return JsonResponse({'status': 'success'})


class FormSubmissionDetailView(FormManagementAccessMixin, View):
    def get(self, request, pk):
        submission = get_object_or_404(
            FormSubmission.objects.select_related('template', 'submitted_by'),
            pk=pk
        )
        template = submission.template

        # 解析关联业务对象
        target = submission.target_object
        related_module = None
        related_entity = None
        related_entity_url = None
        if target:
            from .registry import get_alias_for_model, _TARGET_REGISTRY
            from app_workflow.utils import related_object_router
            alias = get_alias_for_model(type(target))
            cfg = _TARGET_REGISTRY.get(alias) if alias else None
            related_module = cfg.label if cfg else target._meta.verbose_name
            related_entity = cfg.display(target) if cfg else str(target)
            related_entity_url = related_object_router.resolve(target)

        return render(request, 'apps/app_form_management/submission_detail.html', {
            'submission': submission,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
            'submission_data_json': json.dumps(submission.form_data or {}, ensure_ascii=False),
            'related_module': related_module,
            'related_entity': related_entity,
            'related_entity_url': related_entity_url,
        })


# ==========================================
# 3. 表单创建向导
# ==========================================

class FormCreateWizardView(FormManagementAccessMixin, View):
    def get(self, request):
        templates = FormTemplate.objects.filter(is_active=True)
        initial_module = request.GET.get('module', '')
        initial_entity_pk = request.GET.get('entity', '')

        # 验证 initial_module 在白名单中
        if initial_module and get_target(initial_module) is None:
            initial_module = ''

        return render(request, 'apps/app_form_management/form_create_wizard.html', {
            'templates': templates,
            'modules': get_module_choices(),
            'initial_module': initial_module,
            'initial_entity_pk': initial_entity_pk,
        })


class EntitySearchView(FormManagementAccessMixin, View):
    def get(self, request):
        alias = request.GET.get('alias', '')
        search = request.GET.get('search', '')
        pk = request.GET.get('pk', '')
        results = search_entities(alias, search, pk)
        return JsonResponse({'results': results})


# ==========================================
# 4. 我的表单
# ==========================================

class MyDraftsView(FormManagementAccessMixin, View):
    def get(self, request):
        qs = FormSubmission.objects.filter(
            submitted_by=request.user,
            status='DRAFT',
        ).select_related('template', 'content_type').order_by('-updated_at')

        filter_set = MyDraftsFilter(request.GET, queryset=qs)
        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        from .registry import get_alias_for_model, _TARGET_REGISTRY
        from app_workflow.utils import related_object_router

        for d in page_obj.object_list:
            if d.content_type_id:
                model_class = d.content_type.model_class()
                alias = get_alias_for_model(model_class)
                d.target_alias = alias
                cfg = _TARGET_REGISTRY.get(alias)
                d.target_module = cfg.label if cfg else str(d.content_type)
                target_obj = d.target_object
                d.target_display = cfg.display(target_obj) if cfg and target_obj else str(target_obj) if target_obj else '—'
                d.target_url = related_object_router.resolve(target_obj)
            else:
                d.target_module = '—'
                d.target_display = '—'
                d.target_url = None

        return render(request, 'apps/app_form_management/my_drafts.html', {
            'page_obj': page_obj,
            'filter': filter_set,
        })


class MySubmissionsView(FormManagementAccessMixin, View):
    def get(self, request):
        qs = FormSubmission.objects.filter(
            submitted_by=request.user,
            status='SUBMITTED',
        ).select_related('template', 'content_type', 'workflow_instance').order_by('-created_at')

        filter_set = MySubmissionsFilter(request.GET, queryset=qs)

        from .registry import get_alias_for_model, _TARGET_REGISTRY
        from app_workflow.utils import related_object_router

        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))

        for sub in page_obj.object_list:
            if sub.content_type_id:
                model_class = sub.content_type.model_class()
                alias = get_alias_for_model(model_class)
                cfg = _TARGET_REGISTRY.get(alias)
                sub.target_module = cfg.label if cfg else str(sub.content_type)
                target_obj = sub.target_object
                sub.target_display = cfg.display(target_obj) if cfg and target_obj else str(target_obj) if target_obj else '—'
                sub.target_url = related_object_router.resolve(target_obj)
            else:
                sub.target_module = '—'
                sub.target_display = '—'
                sub.target_url = None

        return render(request, 'apps/app_form_management/my_submissions.html', {
            'page_obj': page_obj,
            'filter': filter_set,
        })


class FormSubmissionDeleteView(FormManagementAccessMixin, View):
    def post(self, request, pk):
        submission = get_object_or_404(FormSubmission, pk=pk)
        if submission.submitted_by != request.user:
            return JsonResponse({'status': 'error', 'message': '您没有权限删除此记录。'}, status=403)
        if submission.status != 'DRAFT':
            return JsonResponse({'status': 'error', 'message': '只能删除草稿记录。'}, status=400)
        submission.delete()
        return JsonResponse({'status': 'success'})


# ==========================================
# 5. 项目表单总览
# ==========================================

class ProjectFormListView(ProjectAccessMixin, View):
    """查看项目下所有关联的表单提交（按节点分组）"""
    permission_required = 'app_project.view_project'

    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        self.check_object_permission(project)

        project_ct = ContentType.objects.get_for_model(Project)
        node_ct = ContentType.objects.get_for_model(ProjectNode)

        node_ids = list(project.nodes.values_list('pk', flat=True))

        # 关联到项目节点的表单
        node_submissions = list(
            FormSubmission.objects
            .filter(content_type=node_ct, object_id__in=node_ids)
            .select_related('template', 'workflow_instance', 'submitted_by')
            .order_by('-created_at')
        )

        # 关联到项目本身的表单（不关联具体节点）
        project_submissions = list(
            FormSubmission.objects
            .filter(content_type=project_ct, object_id=project.pk)
            .select_related('template', 'workflow_instance', 'submitted_by')
            .order_by('-created_at')
        )

        # 按节点分组
        grouped = {}  # node_id -> list of submissions
        for sub in node_submissions:
            grouped.setdefault(sub.object_id, []).append(sub)

        # 构建分组列表（保持节点顺序）
        grouped_list = []
        for node in project.cached_nodes:
            if node.pk in grouped:
                grouped_list.append({
                    'node': node,
                    'submissions': grouped[node.pk],
                })

        return render(request, 'apps/app_form_management/project_form_list.html', {
            'project': project,
            'grouped_list': grouped_list,
            'project_submissions': project_submissions,
        })
