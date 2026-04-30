from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory
from .utils import WorkflowEngine
import json
from django.contrib import messages
from django.db.models import Q, Prefetch
from SpiffWorkflow.exceptions import WorkflowException
from django.contrib.auth.models import Group

# ==========================================
# 1. 流程定义管理
# ==========================================

class WorkflowDefinitionListView(LoginRequiredMixin, View):
    """流程定义列表"""
    def get(self, request):
        definitions = WorkflowDefinition.objects.all().select_related('created_by').order_by('-created_at')
        return render(request, 'apps/app_workflow/definition_list.html', {
            'definitions': definitions
        })


class WorkflowEditorView(LoginRequiredMixin, View):
    """BPMN 可视化编辑器页面"""
    def get(self, request, pk=None):
        definition = None
        if pk:
            definition = get_object_or_404(WorkflowDefinition, pk=pk)
        
        initial_xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="_BPMNShape_StartEvent_2" bpmnElement="StartEvent_1">
        <dc:Bounds x="173" y="102" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>"""

        xml_content = definition.bpmn_xml if definition else initial_xml
        
        return render(request, 'apps/app_workflow/editor.html', {
            'definition': definition,
            'xml_content': xml_content
        })


class WorkflowSaveView(LoginRequiredMixin, View):
    """保存流程定义 (AJAX)"""
    def post(self, request):
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


class WorkflowDefinitionDeleteView(LoginRequiredMixin, View):
    """删除流程定义"""
    def post(self, request, pk):
        definition = get_object_or_404(WorkflowDefinition, pk=pk)
        if definition.instances.filter(status='RUNNING').exists():
            return JsonResponse({'status': 'error', 'message': '该流程尚有运行中的实例，无法删除。'})
        
        definition.delete()
        return JsonResponse({'status': 'success'})


class WorkflowToggleActiveView(LoginRequiredMixin, View):
    """切换流程定义的启用状态 (AJAX)"""
    def post(self, request, pk):
        definition = get_object_or_404(WorkflowDefinition, pk=pk)
        definition.is_active = not definition.is_active
        definition.save()
        return JsonResponse({'status': 'success', 'is_active': definition.is_active})


# ==========================================
# 2. 任务与审批处理
# ==========================================

class MyTaskListView(LoginRequiredMixin, View):
    """我的待办任务 (深度性能优化)"""
    def get(self, request):
        user = request.user
        user_groups = set(user.groups.all().values_list('name', flat=True))

        # --- A. 获取所有潜在任务的 ID (分两步避免 SQLite 限制) ---
        # 1. 获取已指派给我的 ID
        assigned_ids = list(WorkflowTask.objects.filter(
            assigned_to=user, status='PENDING'
        ).values_list('pk', flat=True))

        # 2. 获取所有待签收的 ID
        candidate_qs = WorkflowTask.objects.filter(
            assigned_to__isnull=True, status='PENDING'
        ).prefetch_related('candidate_users')

        unassigned_ids = []
        for t in candidate_qs:
            # Python 过滤：检查候选人或候选组
            is_candidate = (user in t.candidate_users.all())
            if not is_candidate and t.candidate_groups:
                is_candidate = bool(user_groups.intersection(set(t.candidate_groups)))
            
            if is_candidate:
                unassigned_ids.append(t.pk)

        # --- B. 发起最终的高性能查询 ---
        from app_project.models import ProjectNode
        # 使用 Prefetch 预加载 ProjectNode 内部的 Project
        node_prefetch = Prefetch(
            'instance__content_object',
            queryset=ProjectNode.objects.select_related('project')
        )

        all_tasks = WorkflowTask.objects.filter(
            pk__in=(assigned_ids + unassigned_ids)
        ).select_related(
            'instance__definition', 
            'instance__started_by',
            'instance__content_type',
        ).prefetch_related(
            'candidate_users',
            node_prefetch # 关键：预加载通用外键及内部关联项
        ).order_by('-created_at').distinct()
        
        # 此时 loop 内不再产生任何数据库查询
        for task in all_tasks:
            obj = task.instance.content_object
            task.related_model_name = obj._meta.model_name if obj else None
            
            task.can_claim = (task.assigned_to is None and 
                              (user in task.candidate_users.all() or 
                               any(g in task.candidate_groups for g in user_groups)))
            task.can_process = (task.assigned_to == user)

        return render(request, 'apps/app_workflow/task_list.html', {
            'tasks': all_tasks
        })


class CompletedTaskListView(LoginRequiredMixin, View):
    """我的已办任务 (深度性能优化)"""
    def get(self, request):
        from app_project.models import ProjectNode
        node_prefetch = Prefetch(
            'instance__content_object',
            queryset=ProjectNode.objects.select_related('project')
        )

        tasks = WorkflowTask.objects.filter(
            assigned_to=request.user,
            status__in=['COMPLETED', 'REJECTED']
        ).select_related(
            'instance__definition', 
            'instance__started_by',
            'instance__content_type',
        ).prefetch_related(
            node_prefetch
        ).order_by('-completed_at')

        for task in tasks:
            obj = task.instance.content_object
            task.related_model_name = obj._meta.model_name if obj else None

        return render(request, 'apps/app_workflow/completed_task_list.html', {
            'tasks': tasks
        })


class TaskClaimView(LoginRequiredMixin, View):
    """签收任务 (AJAX)"""
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


class WorkflowInstanceDetailView(LoginRequiredMixin, View):
    """查看流程实例详情（审批历史等）并处理审批动作"""
    
    def get_context_data(self, request, pk):
        from app_project.models import ProjectNode
        # 详情页也进行同样的深度预加载优化
        instance = get_object_or_404(
            WorkflowInstance.objects.select_related(
                'definition', 'started_by', 'content_type'
            ), 
            pk=pk
        )
        
        # 手动预加载 content_object 及其关联
        if instance.content_type and instance.content_type.model == 'projectnode':
            instance.content_object = ProjectNode.objects.select_related('project').get(pk=instance.object_id)
        
        history = ApprovalHistory.objects.filter(instance=instance).select_related('approver', 'task').order_by('timestamp')
        
        current_task = WorkflowTask.objects.filter(
            instance=instance, 
            assigned_to=request.user, 
            status='PENDING'
        ).first()

        related_object = instance.content_object
        is_project_node = (instance.content_type.model == 'projectnode') if instance.content_type else False

        return {
            'instance': instance,
            'history': history,
            'current_task': current_task,
            'related_object': related_object,
            'is_project_node': is_project_node,
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
