import json
import importlib
import logging
from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.util.task import TaskState
from SpiffWorkflow.bpmn.specs.defaults import UserTask
from SpiffWorkflow.task import Task
from .models import WorkflowInstance, WorkflowTask, ApprovalHistory, WorkflowDefinition
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from .signals import workflow_started, task_created, task_completed, workflow_completed

logger = logging.getLogger(__name__)
User = get_user_model()


# ==========================================
# 关联对象 URL 路由器（通用对接层）
# ==========================================

class RelatedObjectRouter:
    """关联对象元数据路由器。

    供 app_workflow 内部使用，将审批流程的关联对象映射到其详情页 URL、
    显示名称和负责人。各业务模块在 apps.py 中调用 register() 完成注册，
    无需修改 app_workflow 代码。

    使用示例::

        from app_workflow.utils import related_object_router

        # 在业务模块的 apps.py 中注册
        related_object_router.register(
            MyModel,
            url_resolver=lambda obj: reverse('my_detail', kwargs={'pk': obj.pk}),
            display_name_resolver=lambda obj: obj.name,
            person_resolver=lambda obj: obj.manager,
        )

        # 在视图/模板中使用
        url = related_object_router.resolve(obj)
        name = related_object_router.get_display_name(obj)
        person = related_object_router.get_person(obj)
    """

    def __init__(self):
        self._registry = {}

    def register(self, model_class, url_resolver, *, display_name_resolver=None, person_resolver=None):
        """注册模型对应的元数据解析器。

        Parameters
        ----------
        model_class : Model class
            Django 模型类（非代理模型），会按 MRO 向上查找匹配。
        url_resolver : callable
            签名为 ``(obj) -> str | None``，接收模型实例，返回详情页 URL 或 None。
        display_name_resolver : callable, optional
            签名为 ``(obj) -> str``，返回对象的显示名称。未提供时回退到 str(obj)。
        person_resolver : callable, optional
            签名为 ``(obj) -> User | None``，返回对象的负责人/提交人。
        """
        self._registry[model_class] = {
            'url': url_resolver,
            'display_name': display_name_resolver,
            'person': person_resolver,
        }

    def _get_entry(self, obj):
        """按 MRO 顺序查找第一个匹配的注册项"""
        if obj is None:
            return None
        for cls in type(obj).__mro__:
            entry = self._registry.get(cls)
            if entry:
                return entry
        return None

    def resolve(self, obj):
        """解析关联对象的详情页 URL。"""
        entry = self._get_entry(obj)
        if entry:
            return entry['url'](obj)
        return None

    def get_display_name(self, obj):
        """解析关联对象的显示名称。未注册 display_name_resolver 时回退到 str(obj)。"""
        entry = self._get_entry(obj)
        if entry and entry['display_name']:
            return entry['display_name'](obj)
        return str(obj) if obj else None

    def get_person(self, obj):
        """解析关联对象的负责人/提交人。未注册 person_resolver 时返回 None。"""
        entry = self._get_entry(obj)
        if entry and entry['person']:
            return entry['person'](obj)
        return None


# 模块级单例，供各业务模块注册和视图调用
related_object_router = RelatedObjectRouter()



class WorkflowEngine:
    """SpiffWorkflow 引擎封装类 (适配 3.1.2 版本)"""

    @staticmethod
    def _get_serializer():
        return BpmnWorkflowSerializer()

    @staticmethod
    def _create_workflow_from_xml(bpmn_xml_string):
        """从 XML 字符串创建 SpiffWorkflow 对象"""
        parser = BpmnParser()
        
        try:
            bpmn_xml_bytes = bpmn_xml_string.encode('utf-8')
            bpmn_xml_element = etree.fromstring(bpmn_xml_bytes)
            parser.add_bpmn_xml(bpmn_xml_element)
        except Exception as e:
            raise ValueError(f"BPMN XML 解析失败: {str(e)}") from e
        
        process_ids = parser.get_process_ids()
        if not process_ids:
            raise ValueError("BPMN XML 中未找到有效的流程定义")
            
        spec = parser.get_spec(process_ids[0])
        return BpmnWorkflow(spec)

    @classmethod
    def start_instance(cls, definition: WorkflowDefinition, started_by, related_object=None, context_data=None, callback_config=None):
        """
        启动流程实例
        """
        if context_data is None:
            context_data = {}
        if callback_config is None:
            callback_config = {}
        
        workflow = cls._create_workflow_from_xml(definition.bpmn_xml)
        workflow.data.update(context_data)
        
        workflow.do_engine_steps()

        serializer = cls._get_serializer()
        workflow_data = serializer.serialize_json(workflow)

        with transaction.atomic():
            instance = WorkflowInstance.objects.create(
                definition=definition,
                started_by=started_by,
                context_data=context_data,
                spiff_workflow_data=json.loads(workflow_data),
                content_object=related_object,
                callback_config=callback_config
            )
            
            ApprovalHistory.objects.create(
                instance=instance,
                approver=started_by,
                action='START',
                remark="启动流程"
            )

            cls.sync_tasks(instance, workflow)
            
            # 触发流程启动信号
            workflow_started.send(sender=cls, instance=instance)

            return instance

    @classmethod
    def complete_task(cls, task: WorkflowTask, user, action, remark=None):
        """处理/完成一个审批任务"""
        instance = task.instance
        serializer = cls._get_serializer()
        
        workflow_json = json.dumps(instance.spiff_workflow_data)
        workflow = serializer.deserialize_json(workflow_json)
        
        target_task = None
        if task.spiff_instance_id:
            try:
                target_task = workflow.get_task_from_id(int(task.spiff_instance_id))
            except Exception:
                logger.warning(f"WorkflowTask {task.pk} with spiff_instance_id {task.spiff_instance_id} not found in SpiffWorkflow. Falling back to spiff_task_id.")
        
        if not target_task:
            ready_tasks = workflow.get_tasks(state=TaskState.READY)
            for st in ready_tasks:
                st_bpmn_id = getattr(st.task_spec, 'bpmn_id', getattr(st.task_spec, 'id', None))
                if isinstance(st.task_spec, UserTask) and str(st_bpmn_id) == task.spiff_task_id:
                    target_task = st
                    break
        
        if not target_task:
            raise ValueError("未找到匹配的可执行任务或任务已处理")

        with transaction.atomic():
            approval_data = {
                f"{task.spiff_task_id}_action": action,
                f"{task.spiff_task_id}_remark": remark
            }
            
            workflow.data.update(approval_data)
            if hasattr(target_task, 'data'):
                target_task.data.update(approval_data)
            
            target_task.run() 
            workflow.do_engine_steps()
            
            task.status = 'COMPLETED' if action == 'APPROVE' else 'REJECTED'
            task.remark = remark
            task.completed_at = timezone.now()
            task.save()

            ApprovalHistory.objects.create(
                instance=instance,
                task=task,
                approver=user,
                action='APPROVE' if action == 'APPROVE' else 'REJECT',
                remark=remark
            )

            instance.spiff_workflow_data = json.loads(serializer.serialize_json(workflow))
            
            workflow_completed_status = None
            if action == 'REJECT':
                instance.status = 'REJECTED'
                instance.completed_at = timezone.now()
                cls._callback_related_object(instance, 'ROLLBACK')
                workflow_completed_status = 'REJECTED'
            elif workflow.is_completed():
                instance.status = 'COMPLETED'
                instance.completed_at = timezone.now()
                cls._callback_related_object(instance, 'DONE')
                workflow_completed_status = 'COMPLETED'
            
            instance.save()

            # 触发任务完成信号
            task_completed.send(sender=cls, task=task, user=user, action=action)

            # 如果流程结束，触发流程结束信号
            if workflow_completed_status:
                workflow_completed.send(sender=cls, instance=instance, status=workflow_completed_status)

            if instance.status == 'RUNNING':
                cls.sync_tasks(instance, workflow)
            
            return instance

    @classmethod
    def _callback_related_object(cls, instance: WorkflowInstance, target_status: str):
        """回调业务对象"""
        callback_config = instance.callback_config
        handler_path = callback_config.get('handler')
        if not handler_path:
            return

        try:
            module_name, func_name = handler_path.rsplit('.', 1)
            module = importlib.import_module(module_name)
            handler_func = getattr(module, func_name)
            handler_func(instance=instance, target_status=target_status, **callback_config.get('args', {}))
        except Exception as e:
            logger.error(f"Workflow callback error: {e}")

    @classmethod
    def sync_tasks(cls, instance: WorkflowInstance, workflow: BpmnWorkflow):
        """同步 Spiff 内部 Task 到 Django 模型"""
        ready_tasks = workflow.get_tasks(state=TaskState.READY)
        for st in ready_tasks:
            if isinstance(st.task_spec, UserTask):
                st_bpmn_id = getattr(st.task_spec, 'bpmn_id', getattr(st.task_spec, 'id', None))
                if not st_bpmn_id:
                    continue

                workflow_task = WorkflowTask.objects.filter(instance=instance, spiff_instance_id=str(st.id)).first()

                if not workflow_task: # 如果不存在，则创建新任务
                    assigned_to_user, candidate_users_list, candidate_groups_list = cls._resolve_assignee(st, workflow, instance)

                    workflow_task = WorkflowTask.objects.create(
                        instance=instance,
                        task_name=st.task_spec.name or st_bpmn_id,
                        assigned_to=assigned_to_user,
                        spiff_task_id=st_bpmn_id,
                        spiff_instance_id=str(st.id),
                        status='PENDING',
                        candidate_groups=candidate_groups_list,
                    )
                    workflow_task.candidate_users.set(candidate_users_list)
                    
                    # 触发任务创建信号
                    task_created.send(sender=cls, task=workflow_task)
                else: # 如果已存在，确保状态是 PENDING
                    if workflow_task.status != 'PENDING':
                        workflow_task.status = 'PENDING'
                        workflow_task.save()

    CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"

    @classmethod
    def _parse_camunda_assignments(cls, bpmn_xml):
        """
        从 BPMN XML 中解析所有 UserTask 的 camunda 指派属性。
        返回 dict: {bpmn_task_id: {assignee, candidate_users, candidate_groups}}
        """
        assignments = {}
        try:
            root = etree.fromstring(bpmn_xml.encode('utf-8'))
            nsmap = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
                     'camunda': cls.CAMUNDA_NS}
            for ut in root.xpath('//bpmn:userTask', namespaces=nsmap):
                task_id = ut.get('id')
                if not task_id:
                    continue
                info = {}
                assignee = ut.get(f'{{{cls.CAMUNDA_NS}}}assignee')
                if assignee:
                    info['assignee'] = assignee
                cand_users = ut.get(f'{{{cls.CAMUNDA_NS}}}candidateUsers')
                if cand_users:
                    info['candidate_users'] = [u.strip() for u in cand_users.split(',') if u.strip()]
                cand_groups = ut.get(f'{{{cls.CAMUNDA_NS}}}candidateGroups')
                if cand_groups:
                    info['candidate_groups'] = [g.strip() for g in cand_groups.split(',') if g.strip()]
                if info:
                    assignments[task_id] = info
        except Exception as e:
            logger.warning(f"Failed to parse camunda assignments from BPMN XML: {e}")
        return assignments

    @classmethod
    def _resolve_assignee(cls, spiff_task, workflow, instance):
        """
        解析任务的指派人或候选人/组。
        优先级：assignee_map > camunda BPMN 属性 > 流程发起人
        返回 (assigned_to_user, candidate_users_list, candidate_groups_list)
        """
        assigned_to_user = None
        candidate_users_list = []
        candidate_groups_list = []

        st_bpmn_id = getattr(spiff_task.task_spec, 'bpmn_id', None)

        # 1. 从 workflow.data 中的 assignee_map 获取 (优先级最高，可用于动态指派)
        assignee_map = workflow.data.get('assignee_map', {})
        if st_bpmn_id and assignee_map.get(st_bpmn_id):
            assigned_to_user = User.objects.filter(id=assignee_map[st_bpmn_id]).first()
            if assigned_to_user:
                return assigned_to_user, [], []

        # 2. 从 BPMN XML 的 camunda 扩展属性获取
        if st_bpmn_id:
            # 延迟解析：首次调用时解析并缓存到 workflow.data
            camunda_cache = workflow.data.get('_camunda_assignments')
            if camunda_cache is None:
                camunda_cache = cls._parse_camunda_assignments(instance.definition.bpmn_xml)
                workflow.data['_camunda_assignments'] = camunda_cache

            camunda_info = camunda_cache.get(st_bpmn_id, {})
            if camunda_info:
                if camunda_info.get('assignee'):
                    assigned_to_user = User.objects.filter(username=camunda_info['assignee']).first()
                    if assigned_to_user:
                        return assigned_to_user, [], []
                if camunda_info.get('candidate_users'):
                    candidate_users_list = list(User.objects.filter(
                        username__in=camunda_info['candidate_users']
                    ))
                if camunda_info.get('candidate_groups'):
                    candidate_groups_list = list(Group.objects.filter(
                        name__in=camunda_info['candidate_groups']
                    ).values_list('name', flat=True))

        # 3. 单人候选自动指派：无需签收，直接指派
        if not assigned_to_user and len(candidate_users_list) == 1 and not candidate_groups_list:
            assigned_to_user = candidate_users_list[0]
            candidate_users_list = []

        # 4. 最终回退：如果没有明确指派人或候选人，则指派给流程发起人
        if not assigned_to_user and not candidate_users_list and not candidate_groups_list:
            assigned_to_user = instance.started_by

        return assigned_to_user, candidate_users_list, candidate_groups_list
