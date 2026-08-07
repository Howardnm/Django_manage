"""回归测试：流程实例详情页 BPMN 流程图「审批人预解析」。

针对 build_workflow_status_map 的未来节点预解析增强：
启动流程后，整条审批链上尚无 WorkflowTask 记录的未来 userTask 节点，
应按 user_task ID 机制（resolve_assignee 同源）预先解析审批人并显示，
而不是等到审批走到该节点才出现审批人。

覆盖：
  - 五种解析模式在未来节点的预解析：org_role / static_user / static_group /
    assignee_map / camunda:assignee
  - 解析失败时兜底显示发起人
  - 无 camunda 属性、无 WorkflowTask 的裸节点也能进入状态图
  - 当前节点（running）与已完成节点（completed）不被预解析污染
  - 预分配字段不参与 has_active，未来节点状态保持 pending
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_workflow.models import (
    ApprovalHistory, WorkflowDefinition, WorkflowInstance, WorkflowTask,
    WorkflowTaskConfig,
)
from app_workflow.views import build_workflow_status_map, build_workflow_preview_status_map

from app_user.models import (
    Department, OrgRole, OrgRoleAssignment, ReviewGroup, Subsidiary, WorkGroup,
)

User = get_user_model()

BPMN_NS = 'http://www.omg.org/spec/BPMN/20100524/MODEL'
CAMUNDA_NS = 'http://camunda.org/schema/1.0/bpmn'


def _bpmn(task_ids):
    """生成含给定 userTask id（顺序串联）的最小可解析 BPMN。"""
    parts = [
        f'<bpmn:definitions xmlns:bpmn="{BPMN_NS}" '
        f'xmlns:camunda="{CAMUNDA_NS}" targetNamespace="http://bpmn.io/schema/bpmn">',
        '<bpmn:process id="proc" isExecutable="true">',
        '<bpmn:startEvent id="StartEvent"><bpmn:outgoing>f0</bpmn:outgoing></bpmn:startEvent>',
    ]
    prev = 'StartEvent'
    for i, tid in enumerate(task_ids):
        parts.append(
            f'<bpmn:userTask id="{tid}" name="{tid}">'
            f'<bpmn:incoming>f{i}</bpmn:incoming>'
            f'<bpmn:outgoing>f{i + 1}</bpmn:outgoing>'
            f'</bpmn:userTask>'
        )
        parts.append(f'<bpmn:sequenceFlow id="f{i}" sourceRef="{prev}" targetRef="{tid}"/>')
        prev = tid
    parts.append(
        f'<bpmn:sequenceFlow id="f{len(task_ids)}" '
        f'sourceRef="{prev}" targetRef="EndEvent"/>'
    )
    parts.append(
        f'<bpmn:endEvent id="EndEvent"><bpmn:incoming>f{len(task_ids)}</bpmn:incoming>'
        '</bpmn:endEvent>'
    )
    parts.append('</bpmn:process></bpmn:definitions>')
    return ''.join(parts)


def _user(username):
    return User.objects.create_user(
        username=username, email=f'{username}@test.local', password='x',
    )


class StatusMapPreassignBase(TestCase):
    """共享夹具：发起人 + 三位审批人 + 组织架构。"""

    def setUp(self):
        self.initiator = _user('initiator')
        self.leader = _user('leader')
        self.mgr = _user('mgr')
        self.gm = _user('gm')

        # 组织架构：子公司 → 部门 → 工作组（发起人归属其中）
        self.sub = Subsidiary.objects.create(name='上海总部')
        self.dept = Department.objects.create(name='研发中心')
        self.wg = WorkGroup.objects.create(name='配方组', department=self.dept)
        self.wg.members.set([self.initiator])
        self.initiator.department = self.dept
        self.initiator.subsidiary = self.sub
        self.initiator.save()

    def _instance(self, task_ids, context=None, xml=None):
        defn = WorkflowDefinition.objects.create(
            name='流程', bpmn_xml=xml or _bpmn(task_ids),
        )
        return WorkflowInstance.objects.create(
            definition=defn, started_by=self.initiator, status='RUNNING',
            context_data=context or {},
        )

    def _active_task(self, instance, task_id, assigned_to=None, status='PENDING'):
        """模拟已在运行的节点（已生成 WorkflowTask 记录）。"""
        return WorkflowTask.objects.create(
            instance=instance, task_name=task_id, assigned_to=assigned_to,
            spiff_task_id=task_id, status=status,
        )

    def _history(self, instance, task, author, action='APPROVE'):
        return ApprovalHistory.objects.create(
            instance=instance, task=task, approver=author, action=action,
        )

    # ── 组织角色解析辅助 ──────────────────────────────────────

    def _org_role(self, code, name, scope, escalation=True):
        return OrgRole.objects.create(
            code=code, name=name, scope=scope, allow_escalation=escalation,
        )

    def _assign_workgroup_role(self, role, user):
        return OrgRoleAssignment.objects.create(
            role=role, user=user, workgroup=self.wg, is_primary=True,
        )

    def _assign_department_role(self, role, user):
        return OrgRoleAssignment.objects.create(
            role=role, user=user, department=self.dept, is_primary=True,
        )


class OrgRoleFutureNodeTest(StatusMapPreassignBase):
    """org_role 模式：未来节点按发起人组织归属预解析审批人。"""

    def test_org_role_future_node_preassigned_and_pending(self):
        leader_role = self._org_role('group_leader', '组长', 'workgroup')
        self._assign_workgroup_role(leader_role, self.leader)
        mgr_role = self._org_role('dept_manager', '部门经理', 'department')
        self._assign_department_role(mgr_role, self.mgr)
        WorkflowTaskConfig.objects.create(
            task_id='Task_leader', display_name='组长审批',
            resolution_mode='org_role', org_role=leader_role,
        )
        WorkflowTaskConfig.objects.create(
            task_id='Task_mgr', display_name='部门经理审批',
            resolution_mode='org_role', org_role=mgr_role,
        )

        instance = self._instance(['Task_leader', 'Task_mgr'])
        # 首节点已经运行（有 WorkflowTask），次节点仍是未来节点
        self._active_task(instance, 'Task_leader', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)

        # 首节点：显示实际负责人 + running，不被预解析污染
        self.assertEqual(sm['Task_leader']['assigned_to_name'], 'leader')
        self.assertEqual(sm['Task_leader']['display_status'], 'running')
        self.assertNotIn('pre_assigned_name', sm['Task_leader'])

        # 未来节点：预先解析出部门经理 → mgr，状态仍是 pending
        self.assertEqual(sm['Task_mgr']['pre_assigned_name'], 'mgr')
        self.assertEqual(sm['Task_mgr']['display_status'], 'pending')
        self.assertEqual(sm['Task_mgr']['status_label'], '待处理')
        self.assertNotIn('assigned_to_name', sm['Task_mgr'])

    def test_org_role_escalation_resolves_future_node(self):
        """工作组级未指派时，逐级回退到部门级解析未来节点审批人。"""
        leader_role = self._org_role('group_leader', '组长', 'workgroup')
        # 不指派工作组级，仅指派部门级 → 回退命中 mgr
        self._assign_department_role(leader_role, self.mgr)
        WorkflowTaskConfig.objects.create(
            task_id='Task_leader', display_name='组长审批',
            resolution_mode='org_role', org_role=leader_role,
        )

        instance = self._instance(['Task_leader'])
        sm = build_workflow_status_map(instance)

        self.assertEqual(sm['Task_leader']['pre_assigned_name'], 'mgr')


class StaticUserFutureNodeTest(StatusMapPreassignBase):
    """static_user 模式：未来节点预解析为固定审批人。"""

    def test_static_user_future_node_preassigned(self):
        WorkflowTaskConfig.objects.create(
            task_id='Task_gm', display_name='总经理终审',
            resolution_mode='static_user', static_assignee=self.gm,
        )
        instance = self._instance(['Task_leader', 'Task_gm'])
        self._active_task(instance, 'Task_leader', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        self.assertEqual(sm['Task_gm']['pre_assigned_name'], 'gm')
        self.assertEqual(sm['Task_gm']['display_status'], 'pending')


class StaticGroupFutureNodeTest(StatusMapPreassignBase):
    """static_group 模式：未来节点预解析为候选组（待签收）。"""

    def test_static_group_future_node_preassigned_groups(self):
        group = ReviewGroup.objects.create(name='legal_review', is_active=True)
        group.members.set([self.gm])
        WorkflowTaskConfig.objects.create(
            task_id='Task_legal', display_name='法务审核',
            resolution_mode='static_group', review_group=group,
        )
        instance = self._instance(['Task_leader', 'Task_legal'])
        self._active_task(instance, 'Task_leader', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        entry = sm['Task_legal']
        self.assertEqual(entry['pre_assigned_groups'], ['legal_review'])
        self.assertNotIn('pre_assigned_name', entry)
        self.assertEqual(entry['display_status'], 'pending')
        # 未来候选组节点不应带出 DB 层候选成员信息（那是运行中节点才有的）
        self.assertNotIn('candidate_group_members', entry)


class AssigneeMapFutureNodeTest(StatusMapPreassignBase):
    """assignee_map（动态指派）模式：未来节点从 context_data 预解析。"""

    def test_assignee_map_future_node_preassigned(self):
        instance = self._instance(
            ['Task_a', 'Task_b'],
            context={'assignee_map': {'Task_b': self.gm.pk}},
        )
        self._active_task(instance, 'Task_a', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        self.assertEqual(sm['Task_b']['pre_assigned_name'], 'gm')

    def test_assignee_map_missing_node_falls_back_to_initiator(self):
        """assignee_map 只覆盖 Task_a，Task_b 无配置 → 兜底发起人。"""
        instance = self._instance(
            ['Task_a', 'Task_b'],
            context={'assignee_map': {'Task_a': self.leader.pk}},
        )
        self._active_task(instance, 'Task_a', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        self.assertEqual(sm['Task_b']['pre_assigned_name'], 'initiator')


class CamundaFutureNodeTest(StatusMapPreassignBase):
    """camunda:assignee 模式：未来节点从 BPMN XML 预解析。"""

    def test_camunda_assignee_future_node_preassigned(self):
        xml = _bpmn(['Task_a', 'Task_b']).replace(
            'id="Task_b" name="Task_b"',
            'id="Task_b" name="Task_b" camunda:assignee="gm"',
        )
        instance = self._instance(['Task_a', 'Task_b'], xml=xml)
        self._active_task(instance, 'Task_a', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        self.assertEqual(sm['Task_b']['pre_assigned_name'], 'gm')


class FallbackAndCompletenessTest(StatusMapPreassignBase):
    """兜底发起人 + 无 camunda 裸未来节点进入状态图。"""

    def test_unresolvable_future_node_falls_back_to_initiator(self):
        """无任何解析配置的未来节点 → 兜底显示发起人。"""
        instance = self._instance(['Task_a', 'Task_b'])
        self._active_task(instance, 'Task_a', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        self.assertEqual(sm['Task_b']['pre_assigned_name'], 'initiator')
        self.assertEqual(sm['Task_b']['display_status'], 'pending')

    def test_bare_org_role_node_without_camunda_enters_status_map(self):
        """无 camunda 属性、无 WorkflowTask 的裸节点也能进入状态图（曾有 bug）。"""
        instance = self._instance(['Task_only'])
        sm = build_workflow_status_map(instance)
        self.assertIn('Task_only', sm)
        self.assertEqual(sm['Task_only']['display_status'], 'pending')
        # 无任何配置 → 兜底发起人
        self.assertEqual(sm['Task_only']['pre_assigned_name'], 'initiator')

    def test_disabled_config_is_ignored_for_future_node(self):
        """is_active=False 的 WorkflowTaskConfig 不参与未来节点预解析。"""
        static_user = WorkflowTaskConfig.objects.create(
            task_id='Task_b', display_name='终审',
            resolution_mode='static_user', static_assignee=self.gm,
            is_active=False,
        )
        instance = self._instance(['Task_a', 'Task_b'])
        self._active_task(instance, 'Task_a', assigned_to=self.leader)

        sm = build_workflow_status_map(instance)
        # 配置被禁用 → 不命中 static_user → 兜底发起人
        self.assertEqual(sm['Task_b']['pre_assigned_name'], 'initiator')
        self.assertNotEqual(sm['Task_b']['pre_assigned_name'], 'gm')


class ExistingNodeUnaffectedTest(StatusMapPreassignBase):
    """已完成/已运行的节点不被预解析污染。"""

    def test_completed_node_shows_history_not_preassigned(self):
        instance = self._instance(['Task_a', 'Task_b'])
        task = self._active_task(
            instance, 'Task_a', assigned_to=self.leader, status='COMPLETED',
        )
        task.completed_at = None  # 占位，避免日期格式化依赖
        task.save(update_fields=['completed_at'])
        self._history(instance, task, self.leader)

        sm = build_workflow_status_map(instance)
        self.assertEqual(sm['Task_a']['approver_name'], 'leader')
        self.assertEqual(sm['Task_a']['display_status'], 'completed')
        self.assertNotIn('pre_assigned_name', sm['Task_a'])

    def test_running_candidate_node_keeps_db_candidates(self):
        """运行中候选签收节点保留 candidate 信息，且不被预解析覆盖。"""
        group = ReviewGroup.objects.create(name='legal_review', is_active=True)
        group.members.set([self.gm])
        instance = self._instance(['Task_legal', 'Task_b'])
        wt = self._active_task(instance, 'Task_legal', assigned_to=None)
        wt.candidate_users.set([self.gm])
        wt.candidate_groups = ['legal_review']
        wt.save()

        sm = build_workflow_status_map(instance)
        entry = sm['Task_legal']
        self.assertEqual(entry['display_status'], 'running')
        self.assertEqual(entry['candidate_groups'], ['legal_review'])
        self.assertEqual(entry['candidate_usernames'], ['gm'])
        self.assertNotIn('pre_assigned_name', entry)
        self.assertNotIn('pre_assigned_groups', entry)


class WorkflowPreviewStatusMapTest(StatusMapPreassignBase):
    """提交前审批流预览（build_workflow_preview_status_map）。"""

    def _definition(self, task_ids):
        return WorkflowDefinition.objects.create(
            name='预览流程', bpmn_xml=_bpmn(task_ids),
        )

    def test_all_nodes_pending_with_names(self):
        """预览图：所有 userTask 节点均为 pending，并带 BPMN 名称。"""
        defn = self._definition(['Task_a', 'Task_b'])
        sm = build_workflow_preview_status_map(defn, self.initiator)
        self.assertEqual(set(sm.keys()), {'Task_a', 'Task_b'})
        for entry in sm.values():
            self.assertEqual(entry['display_status'], 'pending')
            self.assertEqual(entry['status_label'], '待处理')
        self.assertEqual(sm['Task_a']['task_name'], 'Task_a')

    def test_preview_resolves_org_role_approver(self):
        """预览图按发起人 org_role 预解析审批人。"""
        role = self._org_role('group_leader', '组长', 'workgroup')
        self._assign_workgroup_role(role, self.leader)
        WorkflowTaskConfig.objects.create(
            task_id='Task_a', display_name='组长审批',
            resolution_mode='org_role', org_role=role,
        )
        defn = self._definition(['Task_a'])
        sm = build_workflow_preview_status_map(defn, self.initiator)
        self.assertEqual(sm['Task_a']['pre_assigned_name'], 'leader')

    def test_preview_falls_back_to_initiator(self):
        """预览图：无配置节点 → 兜底显示发起人。"""
        defn = self._definition(['Task_a'])
        sm = build_workflow_preview_status_map(defn, self.initiator)
        self.assertEqual(sm['Task_a']['pre_assigned_name'], 'initiator')

    def test_preview_static_group_candidates(self):
        """预览图：static_group 节点 → 预解析候选组（待签收）。"""
        group = ReviewGroup.objects.create(name='legal_review', is_active=True)
        group.members.set([self.gm])
        WorkflowTaskConfig.objects.create(
            task_id='Task_a', display_name='法务审核',
            resolution_mode='static_group', review_group=group,
        )
        defn = self._definition(['Task_a'])
        sm = build_workflow_preview_status_map(defn, self.initiator)
        self.assertEqual(sm['Task_a']['pre_assigned_groups'], ['legal_review'])
        self.assertNotIn('pre_assigned_name', sm['Task_a'])

    def test_preview_malformed_xml_returns_empty(self):
        """预览图：BPMN XML 非法时返回空映射，不抛异常。"""
        defn = WorkflowDefinition.objects.create(name='坏流程', bpmn_xml='<oops>')
        self.assertEqual(build_workflow_preview_status_map(defn, self.initiator), {})