from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory
from .utils import WorkflowEngine, related_object_router
from .filters import WorkflowTaskFilter, WorkflowInstanceFilter, WorkflowDefinitionFilter
from .mixins import WorkflowAccessMixin
from lxml import etree
import json
from SpiffWorkflow.exceptions import WorkflowException


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
    def get(self, request, pk=None):
        definition = None
        if pk:
            definition = get_object_or_404(WorkflowDefinition, pk=pk)

        return render(request, 'apps/app_workflow/editor.html', {
            'definition': definition,
            'xml_content': definition.bpmn_xml if definition else ''
        })


class WorkflowSaveView(WorkflowAccessMixin, View):
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
    def post(self, request, pk):
        if not request.user.is_superuser:
            return JsonResponse({'status': 'error', 'message': '仅超级管理员可删除流程定义。'}, status=403)

        definition = get_object_or_404(WorkflowDefinition, pk=pk)
        if definition.instances.filter(status='RUNNING').exists():
            return JsonResponse({'status': 'error', 'message': '该流程尚有运行中的实例，无法删除。'})

        definition.delete()
        return JsonResponse({'status': 'success'})


class WorkflowToggleActiveView(WorkflowAccessMixin, View):
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
    def get(self, request):
        user = request.user
        user_groups = set(user.groups.all().values_list('name', flat=True))

        # --- A. 收集任务 ID（已指派 + 候选签收）---
        assigned_ids = list(WorkflowTask.objects.filter(
            assigned_to=user, status='PENDING'
        ).values_list('pk', flat=True))

        candidate_qs = WorkflowTask.objects.filter(
            assigned_to__isnull=True, status='PENDING'
        ).prefetch_related('candidate_users')

        unassigned_ids = []
        for t in candidate_qs:
            is_candidate = (user in t.candidate_users.all())
            if not is_candidate and t.candidate_groups:
                is_candidate = bool(user_groups.intersection(set(t.candidate_groups)))
            if is_candidate:
                unassigned_ids.append(t.pk)

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
    def get(self, request):
        base_qs = WorkflowTask.objects.filter(
            assigned_to=request.user,
            status__in=['COMPLETED', 'REJECTED']
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
    def post(self, request, pk):
        task = get_object_or_404(WorkflowTask, pk=pk)
        user = request.user

        if task.assigned_to is not None:
            return JsonResponse({'status': 'error', 'message': '任务已被签收。'}, status=400)

        user_groups = user.groups.all().values_list('name', flat=True)
        can_claim = (user in task.candidate_users.all() or
                     any(group_name in task.candidate_groups for group_name in user_groups))

        if not can_claim:
            return JsonResponse({'status': 'error', 'message': '您没有权限签收此任务。'}, status=403)

        task.assigned_to = user
        task.save()
        messages.success(request, f"任务 '{task.task_name}' 已成功签收。")
        return JsonResponse({'status': 'success'})


class WorkflowInstanceDetailView(WorkflowAccessMixin, View):

    def _build_process_timeline(self, instance):
        """解析 BPMN XML，按流程序列提取所有 UserTask 节点，匹配数据库状态"""
        nsmap = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL'}
        try:
            root = etree.fromstring(instance.definition.bpmn_xml.encode('utf-8'))
        except Exception:
            return []

        # 1. 构建邻接表 (sequenceFlow sourceRef → targetRef)
        flows = {}
        for sf in root.xpath('//bpmn:sequenceFlow', namespaces=nsmap):
            src, tgt = sf.get('sourceRef'), sf.get('targetRef')
            if src and tgt:
                flows.setdefault(src, []).append(tgt)

        # 2. 从 StartEvent BFS 遍历，提取 UserTask
        starts = root.xpath('//bpmn:startEvent', namespaces=nsmap)
        if not starts:
            return []

        visited = set()
        queue = [starts[0].get('id')]
        visited.add(queue[0])
        timeline = []

        def elem_info(elem_id):
            for tag, kind in [('bpmn:userTask', 'task'),
                              ('bpmn:parallelGateway', 'parallel'),
                              ('bpmn:exclusiveGateway', 'exclusive'),
                              ('bpmn:endEvent', 'end')]:
                el = root.xpath(f'//{tag}[@id="{elem_id}"]', namespaces=nsmap)
                if el:
                    return kind, (el[0].get('name') or elem_id)
            return None, elem_id

        while queue:
            elem_id = queue.pop(0)
            kind, name = elem_info(elem_id)

            if kind == 'task':
                timeline.append({'bpmn_id': elem_id, 'name': name})
            elif kind == 'parallel' or kind == 'exclusive':
                timeline.append({'bpmn_id': elem_id, 'name': name, 'is_gateway': True, 'gateway_type': kind})

            for tgt in flows.get(elem_id, []):
                if tgt not in visited:
                    visited.add(tgt)
                    queue.append(tgt)

        # 3. 解析 camunda 指派信息
        camunda_assignments = WorkflowEngine._parse_camunda_assignments(instance.definition.bpmn_xml)
        for item in timeline:
            if item.get('is_gateway'):
                continue
            camunda_info = camunda_assignments.get(item['bpmn_id'], {})
            parts = []
            if camunda_info.get('assignee'):
                parts.append(camunda_info['assignee'])
            if camunda_info.get('candidate_users'):
                parts.append('候选人: ' + ', '.join(camunda_info['candidate_users']))
            if camunda_info.get('candidate_groups'):
                parts.append('候选组: ' + ', '.join(camunda_info['candidate_groups']))
            item['assignee_label'] = ' / '.join(parts) if parts else '流程发起人'

        # 4. 匹配数据库状态
        db_tasks = {
            t.spiff_task_id: t
            for t in WorkflowTask.objects.filter(instance=instance).select_related('assigned_to').prefetch_related('candidate_users')
        }
        history_by_task = {}
        for h in ApprovalHistory.objects.filter(instance=instance, task__isnull=False).select_related('task', 'approver'):
            history_by_task.setdefault(h.task.spiff_task_id, []).append(h)

        # 预解析候选组的成员列表
        from django.contrib.auth.models import Group
        group_member_map = {}
        all_group_names = set()
        for task in db_tasks.values():
            if task.candidate_groups:
                all_group_names.update(task.candidate_groups)
        if all_group_names:
            for g in Group.objects.filter(name__in=all_group_names).prefetch_related('user_set'):
                group_member_map[g.name] = [u.username for u in g.user_set.all()[:3]]

        for item in timeline:
            if item.get('is_gateway'):
                item['status'] = 'gateway'
                continue

            bpmn_id = item['bpmn_id']
            task = db_tasks.get(bpmn_id)
            item_records = history_by_task.get(bpmn_id, [])

            if task:
                item['task'] = task
                item['status'] = task.status.lower()
                item['completed_at'] = task.completed_at
                item['assigned_to'] = task.assigned_to
                # 待签收：提供候选信息
                if task.assigned_to is None:
                    item['candidate_usernames'] = [u.username for u in task.candidate_users.all()]
                    item['candidate_groups'] = task.candidate_groups
                    if task.candidate_groups:
                        item['candidate_group_members'] = {
                            gn: group_member_map.get(gn, []) for gn in task.candidate_groups
                        }
            else:
                item['status'] = 'pending'
                item['task'] = None

            if item_records:
                latest = item_records[0]
                item['action'] = latest.action
                item['approver'] = latest.approver
                item['remark'] = latest.remark

        return timeline

    def get_context_data(self, request, pk):
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
            assigned_to=request.user,
            status='PENDING'
        ).first()

        related_object = getattr(instance, '_content_object', instance.content_object)
        content_type_model = instance.content_type.model if instance.content_type else None
        related_model_name = related_object._meta.verbose_name if related_object else None
        related_display_name = related_object_router.get_display_name(related_object)
        related_object_url = related_object_router.resolve(related_object)

        process_timeline = self._build_process_timeline(instance)

        return {
            'instance': instance,
            'history': history,
            'current_task': current_task,
            'related_object': related_object,
            'related_display_name': related_display_name,
            'related_model_name': related_model_name,
            'related_object_url': related_object_url,
            'content_type_model': content_type_model,
            'process_timeline': process_timeline,
        }

    def get(self, request, pk):
        context = self.get_context_data(request, pk)
        return render(request, 'apps/app_workflow/instance_detail.html', context)

    def post(self, request, pk):
        context = self.get_context_data(request, pk)
        current_task = context.get('current_task')

        if not current_task:
            messages.error(request, "您没有权限处理此任务或任务已处理。")
            return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))

        action = request.POST.get('action')
        remark = request.POST.get('remark', '').strip()

        if action not in ['APPROVE', 'REJECT']:
            messages.error(request, "无效的审批动作。")
            return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))

        if not remark and action == 'REJECT':
            messages.warning(request, "驳回操作需要填写备注。")
            return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))

        try:
            WorkflowEngine.complete_task(current_task, request.user, action, remark)
            messages.success(request, f"任务已成功{'通过' if action == 'APPROVE' else '驳回'}。")
        except WorkflowException as e:
            messages.error(request, f"流程执行错误: {e}")
        except Exception as e:
            messages.error(request, f"处理任务失败: {e}")

        return redirect(reverse('workflow_instance_detail', kwargs={'pk': pk}))
