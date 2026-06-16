from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from app_user.models import ReviewGroup
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory
from .services import WorkflowService
from .engine import WorkflowEngine
from .utils import related_object_router
from .filters import WorkflowTaskFilter, WorkflowInstanceFilter, WorkflowDefinitionFilter
from .mixins import WorkflowAccessMixin
from .exceptions import (TaskNotFoundError, CancelNotAllowedError, InvalidActionError,
                         ReturnNotAllowedError)
from lxml import etree
import json

User = get_user_model()


def _batch_resolve_content_objects(instances):
    """
    通用批量解析 GenericForeignKey 的 content_object。
    按 content_type 分组后批量获取，避免 N+1 查询。
    将结果作为 _content_object 附加到每个 instance 上。
    """
    if not instances:
        return

    groups = {}
    for obj in instances:
        if obj.content_type_id and obj.object_id:
            groups.setdefault(obj.content_type_id, []).append(obj.object_id)

    results = {}
    for ct_id, obj_ids in groups.items():
        try:
            ct = ContentType.objects.get_for_id(ct_id)
            model = ct.model_class()
            if model:
                for fetched in model.objects.filter(pk__in=set(obj_ids)):
                    results[(ct_id, fetched.pk)] = fetched
        except Exception:
            pass

    for obj in instances:
        key = (obj.content_type_id, obj.object_id)
        obj._content_object = results.get(key)


def _resolve_task_names_from_bpmn(tasks):
    """从 BPMN XML 解析 userTask name 属性，覆盖 task_name（按 definition 缓存）"""
    nsmap = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL'}
    cache = {}
    for t in tasks:
        def_id = t.instance.definition_id
        if def_id not in cache:
            name_map = {}
            try:
                root = etree.fromstring(t.instance.definition.bpmn_xml.encode('utf-8'))
                for ut in root.xpath('//bpmn:userTask', namespaces=nsmap):
                    tid = ut.get('id')
                    tname = ut.get('name')
                    if tid and tname:
                        name_map[tid] = tname
            except Exception:
                pass
            cache[def_id] = name_map
        human_name = cache[def_id].get(t.spiff_task_id)
        if human_name:
            t.task_name = human_name


# ==========================================
# 1. 流程定义管理
# ==========================================

class WorkflowDefinitionListView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.view_workflowdefinition'

    def get(self, request):
        qs = WorkflowDefinition.objects.all().select_related('created_by').order_by('-created_at')
        filter_set = WorkflowDefinitionFilter(request.GET, queryset=qs)
        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))
        return render(request, 'apps/app_workflow/definition_list.html', {
            'page_obj': page_obj,
            'filter': filter_set,
        })


class WorkflowEditorView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.change_workflowdefinition'

    def get(self, request, pk=None):
        definition = None
        if pk:
            definition = get_object_or_404(WorkflowDefinition, pk=pk)

        return render(request, 'apps/app_workflow/editor.html', {
            'definition': definition,
            'xml_content': definition.bpmn_xml if definition else ''
        })


class WorkflowSaveView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.change_workflowdefinition'

    def post(self, request):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可编辑流程定义。'}, status=403)

        data = json.loads(request.body)
        pk = data.get('pk')
        name = data.get('name')
        xml = data.get('xml')
        description = data.get('description', '')

        if pk:
            definition = get_object_or_404(WorkflowDefinition, pk=pk)
            definition.name = name
            definition.bpmn_xml = xml
            definition.description = description
            definition.save()
        else:
            definition = WorkflowDefinition.objects.create(
                name=name,
                bpmn_xml=xml,
                description=description,
                created_by=request.user
            )

        return JsonResponse({'status': 'success', 'pk': definition.pk})


class WorkflowDefinitionDeleteView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.delete_workflowdefinition'

    def post(self, request, pk):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可删除流程定义。'}, status=403)

        definition = get_object_or_404(WorkflowDefinition, pk=pk)
        if definition.instances.filter(status='RUNNING').exists():
            return JsonResponse({'status': 'error', 'message': '该流程尚有运行中的实例，无法删除。'})

        definition.delete()
        return JsonResponse({'status': 'success'})


class WorkflowToggleActiveView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.change_workflowdefinition'

    def post(self, request, pk):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可切换流程启用状态。'}, status=403)

        definition = get_object_or_404(WorkflowDefinition, pk=pk)
        definition.is_active = not definition.is_active
        definition.save()
        return JsonResponse({'status': 'success', 'is_active': definition.is_active})


# ==========================================
# 2. 任务与审批处理
# ==========================================

class MyTaskListView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.view_workflowtask'

    def get(self, request):
        user = request.user
        user_groups = set(user.review_groups.filter(
            is_active=True
        ).values_list('name', flat=True))

        # --- A. 收集任务 ID（已指派 + 候选签收）---
        assigned_ids = list(WorkflowTask.objects.filter(
            assigned_to=user, status='PENDING'
        ).values_list('pk', flat=True))

        # 直接候选用户匹配（DB 层）
        direct_candidate_ids = set(WorkflowTask.objects.filter(
            assigned_to__isnull=True, status='PENDING',
            candidate_users=user,
        ).values_list('pk', flat=True))

        # 候选组匹配（仍需 Python 处理 JSON 字段）
        group_candidate_ids = []
        if user_groups:
            remaining = WorkflowTask.objects.filter(
                assigned_to__isnull=True, status='PENDING'
            ).exclude(pk__in=direct_candidate_ids).only('pk', 'candidate_groups')
            for t in remaining:
                if t.candidate_groups and user_groups.intersection(set(t.candidate_groups)):
                    group_candidate_ids.append(t.pk)

        unassigned_ids = list(direct_candidate_ids) + group_candidate_ids

        # --- B. 批量查询任务及其关联，应用筛选 ---
        base_qs = WorkflowTask.objects.filter(
            pk__in=(assigned_ids + unassigned_ids)
        ).select_related(
            'instance__definition',
            'instance__started_by',
            'instance__content_type',
        ).prefetch_related(
            'candidate_users',
        ).order_by('-created_at').distinct()

        filter_set = WorkflowTaskFilter(request.GET, queryset=base_qs)
        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))
        tasks = page_obj.object_list

        # --- C. 为当前页解析 content_object ---
        instances = [t.instance for t in tasks if t.instance.content_type_id]
        _batch_resolve_content_objects(instances)

        # --- D. 组装展示数据 ---
        _resolve_task_names_from_bpmn(tasks)

        for task in tasks:
            obj = getattr(task.instance, '_content_object', None)
            task.related_model_name = obj._meta.verbose_name if obj else None
            task.related_display_name = related_object_router.get_display_name(obj)
            task.related_object_url = related_object_router.resolve(obj)

            task.can_claim = (task.assigned_to is None and
                              (user in task.candidate_users.all() or
                               any(g in task.candidate_groups for g in user_groups)))
            task.can_process = (task.assigned_to == user)

        return render(request, 'apps/app_workflow/task_list.html', {
            'page_obj': page_obj,
            'filter': filter_set,
        })


class CompletedTaskListView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.view_workflowtask'

    def get(self, request):
        base_qs = WorkflowTask.objects.filter(
            assigned_to=request.user,
            status__in=['COMPLETED', 'REJECTED', 'CANCELED']
        ).select_related(
            'instance__definition',
            'instance__started_by',
            'instance__content_type',
        ).order_by('-completed_at')

        filter_set = WorkflowTaskFilter(request.GET, queryset=base_qs)
        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))
        tasks = page_obj.object_list

        instances = [t.instance for t in tasks if t.instance.content_type_id]
        _batch_resolve_content_objects(instances)

        _resolve_task_names_from_bpmn(tasks)

        for task in tasks:
            obj = getattr(task.instance, '_content_object', None)
            task.related_model_name = obj._meta.verbose_name if obj else None
            task.related_display_name = related_object_router.get_display_name(obj)
            task.related_object_url = related_object_router.resolve(obj)

        return render(request, 'apps/app_workflow/completed_task_list.html', {
            'page_obj': page_obj,
            'filter': filter_set,
        })


class InitiatedInstanceListView(WorkflowAccessMixin, View):
    """我发起的流程：跟踪自己发起的流程实例状态"""
    permission_required = 'app_workflow.view_workflowinstance'

    def get(self, request):
        base_qs = WorkflowInstance.objects.filter(
            started_by=request.user
        ).select_related(
            'definition', 'content_type'
        ).order_by('-started_at')

        filter_set = WorkflowInstanceFilter(request.GET, queryset=base_qs)
        paginator = Paginator(filter_set.qs, 10)
        page_obj = paginator.get_page(request.GET.get('page'))
        instances = list(page_obj.object_list)

        _batch_resolve_content_objects(instances)

        # 批量获取当前页实例的待处理任务
        instance_ids = [i.pk for i in instances]
        current_tasks = WorkflowTask.objects.filter(
            instance_id__in=instance_ids, status='PENDING'
        ).select_related('assigned_to').order_by('created_at')

        pending_map = {}
        for t in current_tasks:
            pending_map.setdefault(t.instance_id, []).append(t)

        _resolve_task_names_from_bpmn(current_tasks)

        results = []
        for inst in instances:
            obj = getattr(inst, '_content_object', None)
            tasks = pending_map.get(inst.pk, [])
            results.append({
                'instance': inst,
                'related_model_name': obj._meta.verbose_name if obj else None,
                'related_display_name': related_object_router.get_display_name(obj),
                'related_person': related_object_router.get_person(obj),
                'related_object': obj,
                'related_object_url': related_object_router.resolve(obj),
                'pending_tasks': tasks,
            })

        return render(request, 'apps/app_workflow/initiated_list.html', {
            'page_obj': page_obj,
            'items': results,
            'filter': filter_set,
        })


class TaskClaimView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.change_workflowtask'

    def post(self, request, pk):
        task = get_object_or_404(WorkflowTask, pk=pk)
        user = request.user

        if task.assigned_to is not None:
            return JsonResponse({'status': 'error', 'message': '任务已被签收。'}, status=400)

        user_groups = set(user.review_groups.filter(
            is_active=True
        ).values_list('name', flat=True))
        can_claim = (user in task.candidate_users.all() or
                     any(g in task.candidate_groups for g in user_groups))

        if not can_claim:
            return JsonResponse({'status': 'error', 'message': '您没有权限签收此任务。'}, status=403)

        try:
            WorkflowService.claim(task, user)
        except InvalidActionError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

        messages.success(request, f"任务 '{task.task_name}' 已成功签收。")
        return JsonResponse({'status': 'success'})


class TaskReassignView(WorkflowAccessMixin, View):
    """转交任务给其他用户"""
    permission_required = 'app_workflow.change_workflowtask'

    def post(self, request, pk):
        task = get_object_or_404(WorkflowTask, pk=pk)
        to_user_id = request.POST.get('to_user_id', '').strip()
        if not to_user_id:
            return JsonResponse({'status': 'error', 'message': '请指定目标用户。'}, status=400)

        # 支持用户名或用户 ID
        try:
            to_user = User.objects.get(pk=int(to_user_id))
        except (ValueError, User.DoesNotExist):
            to_user = get_object_or_404(User, username=to_user_id)

        try:
            WorkflowService.reassign(task, request.user, to_user)
            messages.success(request, f"任务 '{task.task_name}' 已转交给 {to_user.username}。")
        except InvalidActionError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

        return JsonResponse({'status': 'success'})


class TaskReturnView(WorkflowAccessMixin, View):
    """退回任务到前序节点"""
    permission_required = 'app_workflow.change_workflowtask'

    def post(self, request, pk):
        task = get_object_or_404(
            WorkflowTask.objects.select_related('instance'), pk=pk
        )
        target_task_pk = request.POST.get('target_task_pk', '')
        remark = request.POST.get('remark', '').strip()

        if not remark:
            return JsonResponse({'status': 'error', 'message': '退回操作需要填写原因。'}, status=400)
        if not target_task_pk:
            return JsonResponse({'status': 'error', 'message': '请选择退回到哪个节点。'}, status=400)

        # 解析可选步骤表单数据
        step_form_data_json = request.POST.get('step_form_data', '')
        extra_data = {}
        if step_form_data_json:
            try:
                extra_data['step_form_data'] = json.loads(step_form_data_json)
            except (json.JSONDecodeError, ValueError):
                pass

        try:
            if target_task_pk == '0':
                # 退回到发起人（虚拟节点）
                target_task = {'is_initiator': True, 'pk': 0}
                target_name = '发起人（重新填写）'
            else:
                target_task = get_object_or_404(WorkflowTask, pk=target_task_pk)
                target_name = target_task.task_name

            WorkflowService.return_task(task, request.user, target_task, remark,
                                        extra_data=extra_data)
            messages.success(request, f"任务 '{task.task_name}' 已退回到 '{target_name}'。")
        except InvalidActionError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        except ReturnNotAllowedError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        except TaskNotFoundError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

        return JsonResponse({'status': 'success'})


class WorkflowInstanceDetailView(WorkflowAccessMixin, View):
    permission_required = 'app_workflow.view_workflowinstance'

    def _build_status_map(self, instance):
        """构建 BPMN 节点状态映射表, 供前端 bpmn-js 查看器叠加状态与备注"""
        STATUS_LABEL = {
            'completed': '已通过', 'rejected': '已驳回', 'running': '进行中',
            'canceled': '已取消', 'pending': '待处理', 'returned': '已退回',
        }
        bpmn_xml = instance.definition.bpmn_xml
        nsmap = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL'}

        # 1. 解析 camunda 指派信息
        camunda_assignments = WorkflowEngine.parse_camunda_assignments(bpmn_xml)

        # 2. 预加载 DB 数据
        db_tasks = {
            t.spiff_task_id: t
            for t in WorkflowTask.objects.filter(instance=instance).select_related('assigned_to').prefetch_related('candidate_users')
        }
        history_by_task = {}
        for h in ApprovalHistory.objects.filter(instance=instance, task__isnull=False).select_related('task', 'approver').order_by('-timestamp'):
            history_by_task.setdefault(h.task.spiff_task_id, []).append(h)

        group_member_map = {}
        all_group_names = set()
        for task in db_tasks.values():
            if task.candidate_groups:
                all_group_names.update(task.candidate_groups)
        if all_group_names:
            for rg in ReviewGroup.objects.filter(name__in=all_group_names).prefetch_related('members'):
                group_member_map[rg.name] = [u.username for u in rg.members.all()[:3]]

        # 3. 从 BPMN XML 解析 userTask 的 name 属性（优先于 DB 中 task_name）
        try:
            root = etree.fromstring(bpmn_xml.encode('utf-8'))
        except Exception:
            root = None
        bpmn_task_names = {}
        if root is not None:
            for ut in root.xpath('//bpmn:userTask', namespaces=nsmap):
                tid = ut.get('id')
                tname = ut.get('name')
                if tid and tname:
                    bpmn_task_names[tid] = tname

        # 4. 构建任务节点状态映射
        status_map = {}
        all_bpmn_ids = set(camunda_assignments.keys()) | set(db_tasks.keys())
        for bpmn_id in all_bpmn_ids:
            entry = {}
            camunda_info = camunda_assignments.get(bpmn_id, {})
            task = db_tasks.get(bpmn_id)
            history_items = history_by_task.get(bpmn_id, [])

            if task:
                entry['status'] = task.status.lower()
                entry['task_name'] = bpmn_task_names.get(bpmn_id) or task.task_name
                if task.completed_at:
                    entry['completed_at'] = task.completed_at.strftime('%Y-%m-%d %H:%M')
                if task.assigned_to:
                    entry['assigned_to_name'] = task.assigned_to.username
                if not task.assigned_to:
                    entry['candidate_usernames'] = [u.username for u in task.candidate_users.all()]
                    entry['candidate_groups'] = task.candidate_groups
                    if task.candidate_groups:
                        entry['candidate_group_members'] = {
                            gn: group_member_map.get(gn, []) for gn in task.candidate_groups
                        }
            else:
                entry['status'] = 'pending'

            if camunda_info.get('assignee'):
                entry['assignee_label'] = camunda_info['assignee']
            elif camunda_info.get('candidate_users'):
                entry['assignee_label'] = '候选人: ' + ', '.join(camunda_info['candidate_users'])

            if history_items:
                latest = history_items[0]
                entry['approver_name'] = latest.approver.username
                entry['remark'] = latest.remark
                entry['action'] = latest.action

            # ── 状态判定逻辑收归后端 ──
            has_active = bool(
                entry.get('assigned_to_name') or
                entry.get('candidate_usernames') or
                entry.get('candidate_groups')
            )
            status = entry['status']
            if status == 'pending' and has_active:
                entry['display_status'] = 'running'
            else:
                entry['display_status'] = status
            entry['status_label'] = STATUS_LABEL[entry['display_status']]

            status_map[bpmn_id] = entry

        # 5. 解析网关元素并判定颜色状态
        if root is None:
            return status_map

        flows = {}
        for sf in root.xpath('//bpmn:sequenceFlow', namespaces=nsmap):
            src, tgt = sf.get('sourceRef'), sf.get('targetRef')
            if src and tgt:
                flows.setdefault(src, []).append(tgt)

        task_statuses = {bid: status_map[bid]['display_status'] for bid in all_bpmn_ids}

        for tag in ['bpmn:parallelGateway', 'bpmn:exclusiveGateway',
                     'bpmn:inclusiveGateway', 'bpmn:eventBasedGateway']:
            for gw in root.xpath(f'//{tag}', namespaces=nsmap):
                gw_id = gw.get('id')
                if not gw_id or gw_id in status_map:
                    continue

                # BFS 查找下游 UserTask 的状态
                downstream_statuses = []
                visited = set()
                queue = [gw_id]
                while queue and len(visited) < 50:
                    cur = queue.pop(0)
                    if cur in visited:
                        continue
                    visited.add(cur)
                    for nxt in flows.get(cur, []):
                        if nxt in task_statuses:
                            downstream_statuses.append(task_statuses[nxt])
                        elif nxt not in visited:
                            queue.append(nxt)

                if not downstream_statuses:
                    gw_status = 'pending'
                elif all(s == 'completed' for s in downstream_statuses):
                    gw_status = 'completed'
                elif any(s == 'running' for s in downstream_statuses):
                    gw_status = 'running'
                elif any(s == 'rejected' for s in downstream_statuses):
                    gw_status = 'rejected'
                else:
                    gw_status = 'pending'

                status_map[gw_id] = {
                    'status': gw_status,
                    'display_status': gw_status,
                    'status_label': STATUS_LABEL[gw_status],
                    'task_name': gw.get('name') or gw_id,
                    'is_gateway': True,
                }

        return status_map

    def get_context_data(self, **kwargs):
        pk = self.kwargs['pk']
        instance = get_object_or_404(
            WorkflowInstance.objects.select_related('definition', 'started_by', 'content_type'),
            pk=pk
        )

        # 通用：按 content_type 解析关联业务对象
        if instance.content_type_id and instance.object_id:
            _batch_resolve_content_objects([instance])

        history = ApprovalHistory.objects.filter(instance=instance).select_related(
            'approver', 'task'
        ).order_by('timestamp')

        current_task = WorkflowTask.objects.filter(
            instance=instance,
            assigned_to=self.request.user,
            status='PENDING'
        ).first()

        related_object = getattr(instance, '_content_object', instance.content_object)
        content_type_model = instance.content_type.model if instance.content_type else None
        related_model_name = related_object._meta.verbose_name if related_object else None
        related_display_name = related_object_router.get_display_name(related_object)
        related_object_url = related_object_router.resolve(related_object)

        # 项目节点审批流程：节点状态型审批，不存在过程退回，隐藏退回按钮
        is_project_node_workflow = (content_type_model == 'projectnode')

        status_map = self._build_status_map(instance)
        bpmn_xml = instance.definition.bpmn_xml

        return {
            'instance': instance,
            'history': history,
            'current_task': current_task,
            'can_cancel': instance.is_cancelable_by(self.request.user),
            'related_object': related_object,
            'related_display_name': related_display_name,
            'related_model_name': related_model_name,
            'related_object_url': related_object_url,
            'content_type_model': content_type_model,
            'is_project_node_workflow': is_project_node_workflow,
            'status_map': status_map,
            'bpmn_xml': bpmn_xml,
        }

    def get(self, request, pk):
        context = self.get_context_data()
        return render(request, 'apps/app_workflow/instance_detail.html', context)

    def post(self, request, pk):
        context = self.get_context_data()
        current_task = context.get('current_task')

        if not current_task:
            messages.error(request, "您没有权限处理此任务或任务已处理。")
            return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))

        action = request.POST.get('action')
        remark = request.POST.get('remark', '').strip()
        step_form_data_json = request.POST.get('step_form_data', '')

        if action not in ['APPROVE', 'REJECT']:
            messages.error(request, "无效的审批动作。")
            return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))

        if not remark and action == 'REJECT':
            messages.warning(request, "驳回操作需要填写备注。")
            return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))

        extra_data = {}
        if step_form_data_json:
            try:
                extra_data['step_form_data'] = json.loads(step_form_data_json)
            except (json.JSONDecodeError, ValueError):
                pass

        try:
            WorkflowService.complete_task(current_task, request.user, action, remark,
                                          extra_data=extra_data)
            messages.success(request, f"任务已成功{'通过' if action == 'APPROVE' else '驳回'}。")
        except TaskNotFoundError as e:
            messages.error(request, f"任务处理失败: {e}")
        except Exception as e:
            messages.error(request, f"流程执行错误: {e}")

        return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))


# ==========================================
# 3. 流程取消 & 任务转交
# ==========================================

class WorkflowCancelView(WorkflowAccessMixin, View):
    """取消流程实例"""
    permission_required = 'app_workflow.change_workflowinstance'

    def post(self, request, pk):
        instance = get_object_or_404(WorkflowInstance, pk=pk)

        if instance.started_by != request.user and not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅发起人或管理员可取消流程。'}, status=403)

        reason = request.POST.get('reason', '').strip()

        try:
            WorkflowService.cancel(instance, request.user, reason)
            messages.success(request, '流程已取消。')
        except CancelNotAllowedError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

        return JsonResponse({'status': 'success'})
