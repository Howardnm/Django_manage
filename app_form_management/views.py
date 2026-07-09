import json
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.http import JsonResponse
from django.contrib import messages
from django.http import Http404
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
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
    permission_required = 'app_form_management.view_formtemplate'

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
    permission_required = 'app_form_management.add_formtemplate'

    def get(self, request):
        workflows = WorkflowDefinition.objects.filter(is_active=True)
        return render(request, 'apps/app_form_management/template_create.html', {
            'template': None,
            'workflows': workflows,
            'form_config_json': '[]',
            'form_option_json': '{}',
        })

    def post(self, request):

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
    permission_required = 'app_form_management.change_formtemplate'

    def get(self, request, pk):
        template = get_object_or_404(FormTemplate, pk=pk)
        workflows = WorkflowDefinition.objects.filter(is_active=True)
        return render(request, 'apps/app_form_management/template_create.html', {
            'template': template,
            'workflows': workflows,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
        })

    def post(self, request, pk):

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
    permission_required = 'app_form_management.change_formtemplate'

    def post(self, request, pk):
        template = get_object_or_404(FormTemplate, pk=pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        name = data.get('name', '').strip()
        if name:
            template.name = name
        template.group = data.get('group', '')
        template.description = data.get('description', '')
        template.is_active = data.get('is_active', True)
        template.workflow_id = data.get('workflow_id') or None
        template.save()
        return JsonResponse({'status': 'success'})


class FormTemplateDeleteView(FormManagementAccessMixin, View):
    permission_required = 'app_form_management.delete_formtemplate'

    def post(self, request, pk):
        template = get_object_or_404(FormTemplate, pk=pk)
        template.delete()
        return JsonResponse({'status': 'success'})


class FormTemplateDetailView(FormManagementAccessMixin, View):
    permission_required = 'app_form_management.view_formtemplate'

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
    permission_required = 'app_form_management.add_formsubmission'

    def _resolve_target(self, target_alias=None, object_id=None):
        """通过白名单别名解析目标对象。不在 registry 中的 alias 直接 404。"""
        if target_alias and object_id:
            target_model = get_target(target_alias)
            if target_model is None:
                raise Http404
            obj = get_object_or_404(target_model, pk=object_id)
            self._check_target_access(obj)
            return obj
        return None

    def _check_target_access(self, obj):
        """验证用户对目标对象的访问权限"""
        from app_project.models import Project, ProjectNode
        if isinstance(obj, Project):
            if self.request.user.is_superuser:
                return
            if obj.manager_id == self.request.user.pk:
                return
            if obj.members.filter(user=self.request.user).exists():
                return
            raise PermissionDenied("您无权访问该目标项目")
        elif isinstance(obj, ProjectNode):
            self._check_target_access(obj.project)

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

        # 检查是否是退回修订场景
        revision_submission = None
        if not target:
            revision_submission = FormSubmission.objects.filter(
                template=template, submitted_by=request.user, status='SUBMITTED',
                workflow_instance__isnull=False,
                workflow_instance__status='RUNNING',
            ).first()
            if revision_submission and not (revision_submission.workflow_instance.context_data or {}).get('_need_revision'):
                revision_submission = None

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

        existing_data = {}
        if revision_submission:
            existing_data = revision_submission.form_data or {}
        elif existing:
            existing_data = existing.form_data or {}

        return render(request, 'apps/app_form_management/submission_fill.html', {
            'template': template,
            'target': target,
            'target_display': self._get_target_display(target),
            'existing': existing or revision_submission,
            'submit_url': submit_url,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
            'existing_data_json': json.dumps(existing_data, ensure_ascii=False),
            'step_groups_json': template.step_group_json,
            'has_workflow': template.has_workflow,
            'is_multi_step': template.is_multi_step,
            'workflow_restricted': template.is_multi_step and template.has_workflow,
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
            # 优先查找退回修订的已提交记录
            submission = FormSubmission.objects.filter(
                template=template, submitted_by=request.user, status='SUBMITTED',
                workflow_instance__isnull=False,
                workflow_instance__status='RUNNING',
            ).first()
            if submission and not (submission.workflow_instance.context_data or {}).get('_need_revision'):
                submission = None

            if not submission:
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
        if status == 'SUBMITTED' and template.workflow_id:
            from app_workflow.services import WorkflowService
            from app_workflow.engine import WorkflowEngine
            from app_workflow.models import WorkflowTask

            existing_instance = submission.workflow_instance
            is_revision = (existing_instance and
                           existing_instance.status == 'RUNNING' and
                           (existing_instance.context_data or {}).get('_need_revision'))

            if is_revision:
                # 退回修订后重新提交：重建工作流
                try:
                    engine = WorkflowEngine(existing_instance.definition)
                    workflow = engine.create_workflow(
                        context_data={'form_data': form_data, 'remark': remark})
                    existing_instance.spiff_workflow_data = engine.serialize(workflow)
                    ctx = dict(existing_instance.context_data or {})
                    ctx.pop('_need_revision', None)
                    existing_instance.context_data = ctx
                    existing_instance.save()
                    WorkflowService.sync_tasks(existing_instance, workflow, engine)
                except PermissionDenied:
                    raise
                except Exception:
                    pass  # 流程重建失败不阻塞表单提交
            elif not existing_instance:
                # 首次提交：启动新流程
                try:
                    instance = WorkflowService.start(
                        definition=template.workflow,
                        started_by=request.user,
                        related_object=submission,
                        context_data={'form_data': form_data, 'remark': remark},
                    )
                    submission.workflow_instance = instance
                    submission.save(update_fields=['workflow_instance'])
                except PermissionDenied:
                    raise
                except Exception:
                    pass  # 流程启动失败不阻塞表单提交

        return JsonResponse({'status': 'success'})


class FormSubmissionDetailView(FormManagementAccessMixin, View):
    permission_required = 'app_form_management.view_formsubmission'

    def get(self, request, pk):
        submission = get_object_or_404(
            FormSubmission.objects.select_related('template', 'submitted_by', 'workflow_instance__definition'),
            pk=pk
        )
        self.check_object_permission(submission)
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

        # 关联审批流程数据
        workflow_data = None
        current_task = None
        current_task_name = None
        can_edit_step = False
        editable_step_label = ''
        active_step_index = 0
        current_task_form_step = None
        is_workflow_completed = False

        if submission.workflow_instance_id:
            from app_workflow.views import build_workflow_status_map
            from app_workflow.models import ApprovalHistory, WorkflowTask
            wi = submission.workflow_instance
            workflow_data = {
                'instance': wi,
                'status_map': build_workflow_status_map(wi),
                'bpmn_xml': wi.definition.bpmn_xml,
                'history': list(ApprovalHistory.objects.filter(instance=wi).select_related('approver', 'task').order_by('timestamp')),
            }
            is_workflow_completed = wi.status == 'COMPLETED'

            # ── 计算当前激活步骤（不限用户，只看流程进度）──
            if template.is_multi_step and not is_workflow_completed:
                # 取所有待处理任务中最小的 form_step 作为当前激活步骤
                pending_step_task = WorkflowTask.objects.filter(
                    instance=wi, status='PENDING', form_step__isnull=False,
                ).order_by('form_step').first()
                if pending_step_task:
                    active_step_index = next(
                        (i for i, g in enumerate(template.step_groups)
                         if g['step'] == pending_step_task.form_step), 0
                    )

            # ── 当前用户的审批任务（控制编辑权限）──
            current_task = WorkflowTask.objects.filter(
                instance=wi, assigned_to=request.user, status='PENDING'
            ).first()
            if current_task:
                status_entry = workflow_data['status_map'].get(current_task.spiff_task_id, {})
                current_task_name = status_entry.get('task_name') or current_task.task_name

                # 分步填写：当前审批人负责的表单步骤
                if current_task.form_step and template.is_multi_step:
                    can_edit_step = True
                    form_step = current_task.form_step
                    current_task_form_step = form_step
                    for g in template.step_groups:
                        if g['step'] == form_step:
                            editable_step_label = g['label']
                            break
                    if not editable_step_label:
                        editable_step_label = f'第{form_step}步'
                    # 用当前用户的任务步骤更新进度（更精确）
                    active_step_index = next(
                        (i for i, g in enumerate(template.step_groups) if g['step'] == form_step), 0
                    )

        if is_workflow_completed and template.is_multi_step:
            active_step_index = len(template.step_groups)  # 全部标绿

        returnable_targets = current_task.returnable_targets if current_task else []
        need_revision = (workflow_data and
                         (workflow_data['instance'].context_data or {}).get('_need_revision')
                         and request.user == submission.submitted_by)

        return render(request, 'apps/app_form_management/submission_detail.html', {
            'submission': submission,
            'current_task_name': current_task_name,
            'current_task': current_task,
            'returnable_targets': returnable_targets,
            'need_revision': need_revision,
            'can_edit_step': can_edit_step,
            'editable_step_label': editable_step_label,
            'active_step_index': active_step_index,
            'is_workflow_completed': is_workflow_completed,
            'current_task_form_step': current_task_form_step,
            'form_config_json': json.dumps(template.form_config or [], ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
            'submission_data_json': json.dumps(submission.form_data or {}, ensure_ascii=False),
            'step_groups_json': template.step_group_json,
            'field_step_map_json': json.dumps(template.get_field_step_map(), ensure_ascii=False),
            'related_module': related_module,
            'related_entity': related_entity,
            'related_entity_url': related_entity_url,
            'workflow_data': workflow_data,
        })


# ==========================================
# 3. 表单创建向导
# ==========================================

class FormCreateWizardView(FormManagementAccessMixin, View):
    permission_required = 'app_form_management.view_formtemplate'

    def get(self, request):
        templates = FormTemplate.objects.filter(is_active=True).order_by('group', 'name')
        initial_module = request.GET.get('module', '')
        initial_entity_pk = request.GET.get('entity', '')

        # 验证 initial_module 在白名单中
        if initial_module and get_target(initial_module) is None:
            initial_module = ''

        # 预填实体信息（只读，不允许手动修改）
        initial_module_label = ''
        initial_entity_label = ''
        if initial_module and initial_entity_pk:
            target_model = get_target(initial_module)
            if target_model:
                from .registry import _TARGET_REGISTRY
                cfg = _TARGET_REGISTRY.get(initial_module)
                initial_module_label = cfg.label if cfg else ''
                try:
                    obj = target_model.objects.get(pk=int(initial_entity_pk))
                    initial_entity_label = cfg.display(obj) if cfg else str(obj)
                except Exception:
                    initial_module = ''
                    initial_entity_pk = ''

        # 按分组整理模板 — 有分组的在前，未分组的末尾
        template_groups = []
        seen = set()
        ungrouped = []
        for tpl in templates:
            if tpl.group:
                if tpl.group not in seen:
                    seen.add(tpl.group)
                    template_groups.append({'name': tpl.group, 'templates': [], 'muted': False})
                template_groups[-1]['templates'].append(tpl)
            else:
                ungrouped.append(tpl)
        if ungrouped:
            template_groups.append({'name': '', 'templates': ungrouped, 'muted': True})

        return render(request, 'apps/app_form_management/form_create_wizard.html', {
            'template_groups': template_groups,
            'modules': get_module_choices(),
            'initial_module': initial_module,
            'initial_entity_pk': initial_entity_pk,
            'initial_module_label': initial_module_label,
            'initial_entity_label': initial_entity_label,
            'is_bound_target': bool(initial_module and initial_entity_pk),
        })


class EntitySearchView(FormManagementAccessMixin, View):
    permission_required = 'app_form_management.view_formsubmission'

    def get(self, request):
        alias = request.GET.get('alias', '')
        search = request.GET.get('search', '')
        results = search_entities(alias, search, user=request.user)
        return JsonResponse({'results': results})


# ==========================================
# 4. 我的表单
# ==========================================

class MyDraftsView(FormManagementAccessMixin, View):
    permission_required = 'app_form_management.view_formsubmission'

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
    permission_required = 'app_form_management.view_formsubmission'

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
    permission_required = 'app_form_management.delete_formsubmission'

    def post(self, request, pk):
        submission = get_object_or_404(FormSubmission, pk=pk)
        try:
            self.check_object_permission(submission)
        except PermissionDenied as e:
            return JsonResponse({'status': 'error', 'message': str(e) or '您没有权限删除此记录。'}, status=403)
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
