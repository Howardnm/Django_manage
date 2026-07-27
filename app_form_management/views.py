import json
import uuid as _uuid

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.http import JsonResponse
from django.contrib import messages
from django.http import Http404
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.middleware.csrf import get_token

from .models import FormTemplate, FormSubmission
from app_workflow.models import WorkflowDefinition
from app_project.models import Project, ProjectNode
from app_project.mixins import ProjectAccessMixin
from .mixins import FormManagementAccessMixin
from .services import submission_service
from .registry import get_target, get_module_choices, search_entities
from .filters import FormTemplateFilter, MyDraftsFilter, MySubmissionsFilter
from .rule_injector import inject_upload_config, enrich_upload_form_data


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

    def get(self, request, template_pk, target_alias=None, obj_pk=None, submission_pk=None):
        template = get_object_or_404(FormTemplate, pk=template_pk)
        target = self._resolve_target(target_alias=target_alias, object_id=obj_pk)

        if submission_pk:
            # ── 编辑模式：按 PK 精确加载已有提交 ──
            existing = get_object_or_404(
                FormSubmission, pk=submission_pk, template=template,
            )
            if existing.submitted_by_id != request.user.pk:
                raise PermissionDenied('您没有权限编辑该提交')
            if existing.status == 'SUBMITTED':
                ctx = (existing.workflow_instance.context_data
                       if existing.workflow_instance_id else {}) or {}
                if not ctx.get('_need_revision'):
                    raise PermissionDenied('该提交不处于退回修订状态')
            submit_url = reverse('form_submission_edit', kwargs={
                'template_pk': template_pk,
                'submission_pk': submission_pk,
            })
            existing_data = existing.form_data or {}
        else:
            # ── 新建模式：永远创建全新 FormSubmission ──
            if target:
                existing = FormSubmission.objects.create(
                    template=template,
                    target_object=target,
                    submitted_by=request.user,
                    status='DRAFT',
                )
                submit_url = reverse('form_submission_fill_target', kwargs={
                    'template_pk': template_pk,
                    'target_alias': target_alias,
                    'obj_pk': obj_pk,
                })
            else:
                existing = FormSubmission.objects.create(
                    template=template,
                    submitted_by=request.user,
                    status='DRAFT',
                )
                submit_url = reverse('form_submission_fill', kwargs={
                    'template_pk': template_pk,
                })
            existing_data = {}

        # ── 公共逻辑：注入上传配置 + 富化数据 ──
        csrf_token = get_token(request)
        configured_rules = inject_upload_config(
            template.form_config or [],
            submission_id=existing.pk,
            csrf_token=csrf_token,
            is_editable=True,
        )
        if existing_data:
            existing_data = enrich_upload_form_data(
                existing_data, configured_rules, existing,
            )

        return render(request, 'apps/app_form_management/submission_fill.html', {
            'template': template,
            'target': target,
            'target_display': self._get_target_display(target),
            'existing': existing,
            'submit_url': submit_url,
            'form_config_json': json.dumps(configured_rules, ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
            'existing_data_json': json.dumps(existing_data, ensure_ascii=False),
            'step_groups_json': template.step_group_json,
            'has_workflow': template.has_workflow,
            'is_multi_step': template.is_multi_step,
            'workflow_restricted': template.is_multi_step and template.has_workflow,
        })

    def post(self, request, template_pk, target_alias=None, obj_pk=None, submission_pk=None):
        template = get_object_or_404(FormTemplate, pk=template_pk)
        target = self._resolve_target(target_alias=target_alias, object_id=obj_pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': '无效的JSON数据。'}, status=400)

        form_data = data.get('form_data', {})
        status = data.get('status', 'SUBMITTED')
        remark = data.get('remark', '')

        if submission_pk:
            # ── 编辑模式：按 PK 精确更新 ──
            submission = get_object_or_404(
                FormSubmission, pk=submission_pk, template=template,
            )
            if submission.submitted_by_id != request.user.pk:
                return JsonResponse(
                    {'status': 'error', 'message': '您没有权限编辑该提交'},
                    status=403,
                )
            submission.form_data = form_data
            submission.remark = remark
            submission.status = status
            submission.save()
        else:
            # ── 新建模式：用 submission_id 定位 get() 阶段创建的草稿 ──
            submission_id = data.get('submission_id')
            submission = (get_object_or_404(FormSubmission, pk=submission_id)
                          if submission_id else None)
            if submission:
                if submission.submitted_by_id != request.user.pk:
                    return JsonResponse(
                        {'status': 'error', 'message': '您没有权限编辑该提交'},
                        status=403,
                    )
                submission.form_data = form_data
                submission.remark = remark
                submission.status = status
                submission.save()
            else:
                # 兜底：submission_id 丢失时创建新记录
                submission = FormSubmission.objects.create(
                    template=template,
                    submitted_by=request.user,
                    form_data=form_data,
                    status=status,
                    remark=remark,
                )
                if target:
                    submission.content_type = ContentType.objects.get_for_model(target)
                    submission.object_id = target.pk
                    submission.save()

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

        # 注入上传配置到 form-create rules
        # is_editable 仅当当前用户是活跃审批人时才为 True，
        # 否则上传组件设 disabled=True 且不注入 beforeRemove 钩子
        csrf_token = get_token(request)
        configured_rules = inject_upload_config(
            template.form_config or [],
            submission_id=submission.pk,
            csrf_token=csrf_token,
            is_editable=can_edit_step,
        )

        # 将 upload 字段的 URL 字符串转为 {url, name} 对象，使文件名正确显示
        submission_data = submission.form_data or {}
        if submission_data:
            submission_data = enrich_upload_form_data(
                submission_data, configured_rules, submission,
            )

        # 查询该提交的所有附件
        from app_attachment.models import Attachment
        att_ct = ContentType.objects.get_for_model(FormSubmission)
        attachments = list(
            Attachment.objects.filter(
                content_type=att_ct, object_id=submission.pk, is_deleted=False,
            ).select_related('uploader').order_by('-uploaded_at')
        )

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
            'form_config_json': json.dumps(configured_rules, ensure_ascii=False),
            'form_option_json': json.dumps(template.form_option or {}, ensure_ascii=False),
            'submission_data_json': json.dumps(submission_data, ensure_ascii=False),
            'step_groups_json': template.step_group_json,
            'field_step_map_json': json.dumps(template.get_field_step_map(), ensure_ascii=False),
            'related_module': related_module,
            'related_entity': related_entity,
            'related_entity_url': related_entity_url,
            'workflow_data': workflow_data,
            'attachments': attachments,
        })


# ==========================================
# 2.5 表单附件上传 / 删除 API
# ==========================================

def _url_matches(value, target_url):
    """判断 form_data 中的值与目标下载 URL 是否匹配。

    兼容两种存储格式：字符串 URL 和 {url, name} 对象。
    """
    if isinstance(value, str):
        return value == target_url
    if isinstance(value, dict):
        return value.get('url') == target_url
    return False


def _sync_form_data_add(submission, field_name, file_entry):
    """将上传文件信息追加到 form_data 对应字段中。"""
    form_data = dict(submission.form_data or {})
    field_files = form_data.get(field_name)
    if not isinstance(field_files, list):
        field_files = []
    field_files.append(file_entry)
    form_data[field_name] = field_files
    submission.form_data = form_data
    submission.save(update_fields=['form_data'])


def _sync_form_data_remove(attachment):
    """从 form_data 中移除被删除附件对应的条目。

    通过 attachment.group_key 定位字段名，
    通过 attachment.download_token 构建下载 URL 进行匹配。
    """
    from app_form_management.models import FormSubmission as FSModel

    group_key = attachment.group_key or ''
    if not group_key.startswith('field:'):
        return
    field_name = group_key[len('field:'):]

    download_url = reverse('attachment:download', kwargs={
        'token': str(attachment.download_token),
    })

    try:
        submission = FSModel.objects.get(pk=attachment.object_id)
    except FSModel.DoesNotExist:
        return

    form_data = dict(submission.form_data or {})
    field_files = form_data.get(field_name)
    if not isinstance(field_files, list):
        return

    form_data[field_name] = [
        v for v in field_files
        if not _url_matches(v, download_url)
    ]
    submission.form_data = form_data
    submission.save(update_fields=['form_data'])


class FormUploadView(FormManagementAccessMixin, View):
    """
    POST /forms/api/upload/
    Receives file upload from form-create fcUpload component.
    Creates an Attachment record parented to the FormSubmission,
    with group_key derived from the field name.
    """

    def post(self, request):
        submission_id = request.POST.get('submission_id', '')
        field_name = request.POST.get('field_name', '')
        file = request.FILES.get('file')

        if not submission_id or not file:
            return JsonResponse(
                {'status': 'error', 'message': '缺少必要参数 (submission_id, file)'},
                status=400,
            )

        try:
            submission_id = int(submission_id)
        except (ValueError, TypeError):
            return JsonResponse(
                {'status': 'error', 'message': '无效的 submission_id'},
                status=400,
            )

        submission = get_object_or_404(FormSubmission, pk=submission_id)
        try:
            _check_attachment_modify_permission(request.user, submission, field_name)
        except PermissionDenied as e:
            return JsonResponse(
                {'status': 'error', 'message': str(e)},
                status=403,
            )

        ct = ContentType.objects.get_for_model(FormSubmission)
        attachment = self._create_attachment(ct, submission, file, field_name, request.user)

        download_url = reverse('attachment:download', kwargs={
            'token': str(attachment.download_token),
        })
        file_entry = {
            'url': download_url,
            'name': attachment.display_name,
        }

        # 同步更新 form_data，无需等待用户手动保存
        _sync_form_data_add(submission, field_name, file_entry)

        return JsonResponse({'data': file_entry})

    def _create_attachment(self, ct, submission, file, field_name, uploader):
        """Create an Attachment record linked to the submission."""
        from app_attachment.models import Attachment

        attachment = Attachment(
            content_type=ct,
            object_id=submission.pk,
            file=file,
            uploader=uploader,
            category='OTHER',
            group_key=f'field:{field_name}' if field_name else '',
        )
        attachment.save()
        return attachment


def _check_attachment_modify_permission(user, submission, field_name):
    """统一附件操作权限（上传/删除通用），无超管豁免。

    单步骤表单：仅提交者在草稿或退回修订时可操作。
    多步骤表单：草稿/退回修订=提交者；审批中=仅当前步骤审批人。
    """
    # ── 草稿：仅提交者 ──
    if submission.status == 'DRAFT':
        if submission.submitted_by_id != user.pk:
            raise PermissionDenied('草稿状态下仅提交者可操作附件')
        return

    # ── 退回修订：仅提交者 ──
    if submission.workflow_instance_id:
        ctx = submission.workflow_instance.context_data or {}
        if ctx.get('_need_revision'):
            if submission.submitted_by_id != user.pk:
                raise PermissionDenied('退回修订状态下仅提交者可操作附件')
            return

    # ── 已提交状态 ──
    if submission.status == 'SUBMITTED':
        # 单步骤：审批中任何人不可操作
        if not submission.template.is_multi_step:
            raise PermissionDenied('当前审批状态下不可操作附件')

        # 多步骤：检查字段步骤归属 + 当前审批人
        _check_multi_step_field_permission(user, submission, field_name)
        return

    raise PermissionDenied('当前状态下不可操作附件')


def _check_multi_step_field_permission(user, submission, field_name):
    """多步骤表单：验证用户是当前步骤审批人，且字段属于该步骤。"""
    if not submission.workflow_instance_id:
        raise PermissionDenied('该提交未关联审批流程')

    field_step = submission.template.get_field_step_map().get(field_name, 1)

    from app_workflow.models import WorkflowTask
    task = WorkflowTask.objects.filter(
        instance_id=submission.workflow_instance_id,
        assigned_to=user,
        status='PENDING',
        form_step=field_step,
    ).first()

    if not task:
        raise PermissionDenied('当前审批步骤无权操作该字段的附件')


class FormUploadDeleteView(FormManagementAccessMixin, View):
    """
    POST /forms/api/upload/delete/
    Soft-deletes an Attachment by its download_token.
    Permission is enforced by _check_attachment_modify_permission in post().
    Called by the beforeRemove hook in fcUpload.
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {'status': 'error', 'message': '无效的JSON数据'},
                status=400,
            )

        token = data.get('token', '').strip()
        if not token:
            return JsonResponse(
                {'status': 'error', 'message': '缺少令牌参数'},
                status=400,
            )

        try:
            _uuid.UUID(token)
        except (ValueError, AttributeError):
            return JsonResponse(
                {'status': 'error', 'message': '无效的令牌格式'},
                status=400,
            )

        from app_attachment.models import Attachment
        attachment = get_object_or_404(
            Attachment,
            download_token=token,
            is_deleted=False,
        )

        # 提取字段名并校验权限
        field_name = ''
        if attachment.group_key and attachment.group_key.startswith('field:'):
            field_name = attachment.group_key[len('field:'):]

        from app_form_management.models import FormSubmission as FSModel
        submission = get_object_or_404(FSModel, pk=attachment.object_id)
        try:
            _check_attachment_modify_permission(request.user, submission, field_name)
        except PermissionDenied as e:
            return JsonResponse(
                {'status': 'error', 'message': str(e)},
                status=403,
            )

        attachment.is_deleted = True
        attachment.save(update_fields=['is_deleted'])

        # 同步移除 form_data 中的对应条目
        _sync_form_data_remove(attachment)

        return JsonResponse({'status': 'success'})


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

        # 查询当前用户在这些模板中是否有草稿
        user_draft_template_ids = set(
            FormSubmission.objects.filter(
                template__in=templates,
                submitted_by=request.user,
                status='DRAFT',
            ).values_list('template_id', flat=True)
        )

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
            'user_draft_template_ids': user_draft_template_ids,
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
