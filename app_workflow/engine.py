import json
import logging
from lxml import etree
from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.util.task import TaskState
from SpiffWorkflow.bpmn.specs.defaults import UserTask
from django.contrib.auth import get_user_model
from app_user.models import ReviewGroup
from .models import WorkflowDefinition
from .exceptions import WorkflowError, WorkflowParseError

logger = logging.getLogger(__name__)
User = get_user_model()


class WorkflowEngine:
    """SpiffWorkflow 引擎封装 (实例化, 绑定流程定义)"""

    CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"

    def __init__(self, definition: WorkflowDefinition):
        self.definition = definition
        self._serializer = BpmnWorkflowSerializer()

    # ── 生命周期 ──────────────────────────────────────────────

    def create_workflow(self, context_data: dict | None = None) -> BpmnWorkflow:
        """解析 BPMN XML → BpmnWorkflow, 执行初始引擎步骤"""
        parser = BpmnParser()
        try:
            bpmn_xml_element = etree.fromstring(self.definition.bpmn_xml.encode('utf-8'))
            parser.add_bpmn_xml(bpmn_xml_element)
        except Exception as e:
            raise WorkflowParseError(f"BPMN XML 解析失败: {e}") from e

        process_ids = parser.get_process_ids()
        if not process_ids:
            raise WorkflowParseError("BPMN XML 中未找到有效的流程定义")

        spec = parser.get_spec(process_ids[0])
        workflow = BpmnWorkflow(spec)

        if context_data:
            workflow.data.update(context_data)

        self._do_engine_steps(workflow)
        return workflow

    def deserialize(self, data: dict) -> BpmnWorkflow:
        """从 JSON dict 反序列化工作流"""
        return self._serializer.deserialize_json(json.dumps(data))

    def serialize(self, workflow: BpmnWorkflow) -> dict:
        """序列化工作流为 JSON dict"""
        return json.loads(self._serializer.serialize_json(workflow))

    def _do_engine_steps(self, workflow: BpmnWorkflow):
        """包装 do_engine_steps, 统一抛 WorkflowError"""
        try:
            workflow.do_engine_steps()
        except Exception as e:
            raise WorkflowError(f"流程引擎执行失败: {e}") from e

    # ── 任务操作 ──────────────────────────────────────────────

    def complete(self, workflow: BpmnWorkflow, spiff_task, action: str,
                 extra_data: dict | None = None) -> bool:
        """执行审批任务并推进流程。返回 workflow.is_completed()"""
        st_bpmn_id = getattr(spiff_task.task_spec, 'bpmn_id',
                             getattr(spiff_task.task_spec, 'id', None))
        st_name = spiff_task.task_spec.name or str(st_bpmn_id)

        approval_data = {
            f"{st_bpmn_id}_action": action,
            f"{st_name}_action": action,
        }
        if extra_data:
            if 'remark' in extra_data:
                approval_data[f"{st_bpmn_id}_remark"] = extra_data['remark']
            approval_data.update(extra_data)

        workflow.data.update(approval_data)
        if hasattr(spiff_task, 'data'):
            spiff_task.data.update(approval_data)

        spiff_task.run()
        self._do_engine_steps(workflow)
        return workflow.is_completed()

    def get_ready_user_tasks(self, workflow: BpmnWorkflow) -> list:
        """获取所有处于 READY 状态的 UserTask"""
        return [t for t in workflow.get_tasks(state=TaskState.READY)
                if isinstance(t.task_spec, UserTask)]

    # ── 指派解析 ──────────────────────────────────────────────

    def resolve_assignee(self, spiff_task, workflow: BpmnWorkflow,
                         instance) -> tuple:
        """解析任务指派人。
        优先级: assignee_map > camunda BPMN 属性 > 单人候选自动指派 > 流程发起人
        返回 (assigned_to_user, candidate_users_list, candidate_groups_list)
        """
        assigned_to_user = None
        candidate_users_list = []
        candidate_groups_list = []

        st_bpmn_id = getattr(spiff_task.task_spec, 'bpmn_id', None)

        # 1. workflow.data 中的 assignee_map (动态指派, 优先级最高)
        assignee_map = workflow.data.get('assignee_map', {})
        if st_bpmn_id and assignee_map.get(st_bpmn_id):
            assigned_to_user = User.objects.filter(id=assignee_map[st_bpmn_id]).first()
            if assigned_to_user:
                return assigned_to_user, [], []

        # 2. BPMN XML camunda 扩展属性 (延迟解析, 缓存到 workflow.data)
        if st_bpmn_id:
            camunda_cache = workflow.data.get('_camunda_assignments')
            if camunda_cache is None:
                camunda_cache = self.parse_camunda_assignments(self.definition.bpmn_xml)
                workflow.data['_camunda_assignments'] = camunda_cache

            camunda_info = camunda_cache.get(st_bpmn_id, {})
            if camunda_info:
                if camunda_info.get('assignee'):
                    assigned_to_user = User.objects.filter(
                        username=camunda_info['assignee']).first()
                    if assigned_to_user:
                        return assigned_to_user, [], []
                if camunda_info.get('candidate_users'):
                    candidate_users_list = list(User.objects.filter(
                        username__in=camunda_info['candidate_users']))
                if camunda_info.get('candidate_groups'):
                    candidate_groups_list = list(ReviewGroup.objects.filter(
                        name__in=camunda_info['candidate_groups'],
                        is_active=True,
                    ).values_list('name', flat=True))

        # 3. 单人候选自动指派
        if not assigned_to_user and len(candidate_users_list) == 1 and not candidate_groups_list:
            assigned_to_user = candidate_users_list[0]
            candidate_users_list = []

        # 4. 最终回退: 流程发起人
        if not assigned_to_user and not candidate_users_list and not candidate_groups_list:
            assigned_to_user = instance.started_by

        return assigned_to_user, candidate_users_list, candidate_groups_list

    # ── 静态工具 ──────────────────────────────────────────────

    @staticmethod
    def parse_camunda_assignments(bpmn_xml: str) -> dict:
        """解析 BPMN XML 中所有 UserTask 的 camunda 指派属性。
        返回 {bpmn_task_id: {assignee, candidate_users, candidate_groups}}
        """
        assignments = {}
        try:
            root = etree.fromstring(bpmn_xml.encode('utf-8'))
            nsmap = {
                'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
                'camunda': WorkflowEngine.CAMUNDA_NS,
            }
            for ut in root.xpath('//bpmn:userTask', namespaces=nsmap):
                task_id = ut.get('id')
                if not task_id:
                    continue
                info = {}
                assignee = ut.get(f'{{{WorkflowEngine.CAMUNDA_NS}}}assignee')
                if assignee:
                    info['assignee'] = assignee
                cand_users = ut.get(f'{{{WorkflowEngine.CAMUNDA_NS}}}candidateUsers')
                if cand_users:
                    info['candidate_users'] = [u.strip() for u in cand_users.split(',') if u.strip()]
                cand_groups = ut.get(f'{{{WorkflowEngine.CAMUNDA_NS}}}candidateGroups')
                if cand_groups:
                    info['candidate_groups'] = [g.strip() for g in cand_groups.split(',') if g.strip()]
                form_step = ut.get(f'{{{WorkflowEngine.CAMUNDA_NS}}}formStep')
                if form_step:
                    try:
                        info['form_step'] = int(form_step)
                    except (ValueError, TypeError):
                        pass
                form_step_label = ut.get(f'{{{WorkflowEngine.CAMUNDA_NS}}}formStepLabel')
                if form_step_label:
                    info['form_step_label'] = form_step_label
                if info:
                    assignments[task_id] = info
        except Exception as e:
            logger.warning(f"Failed to parse camunda assignments from BPMN XML: {e}")
        return assignments
