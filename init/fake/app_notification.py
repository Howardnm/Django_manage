"""
app_notification 伪数据生成器

业务逻辑：
  - Notification：站内通知，包含 recipient(接收方) / actor(操作方) / verb(动作描述) / unread
  - 审批实例：为部分项目创建 WorkflowInstance → WorkflowTask → ApprovalHistory
    任务节点与 BPMN UserTask 严格对应（id + name），spiff_task_id 沿用 BPMN 元素 ID
"""

import random
from django.db import transaction
from django.utils import timezone
from ._base import FakeContext, fake, pick_one, pick, COUNT_NOTIFICATIONS


# ---------------------------------------------------------------------------
# BPMN 用户任务映射 — 与 app_workflow.py 中定义的 XML 保持一致
# ---------------------------------------------------------------------------
BPMN_TASK_MAP = {
    '研发评审流程': [
        ('Task_dept_mgr',  '部门经理审批'),
        ('Task_director',  '研发总监审批'),
        ('Task_process',   '工艺复核'),
        ('Task_sales',     '销售确认'),
    ],
    '量产放行流程': [
        ('Task_qa_review',     '品质审核'),
        ('Task_prod_confirm',  '生产确认'),
        ('Task_final_approve', '总监终审'),
    ],
    '异常审批流程': [
        ('Task_reporter',      '异常说明'),
        ('Task_dept_head',     '部门负责人审核'),
        ('Task_dir_decision',  '总监裁决'),
    ],
}


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[16/16] Creating notifications & approval instances...")

    # =====================================================================
    # 1. Notification
    # =====================================================================
    from app_notification.models import Notification

    verbs = [
        "created project", "updated node", "submitted approval",
        "uploaded file", "reported failure", "added formula",
        "completed review", "modified BOM", "submitted test data",
    ]
    for _ in range(COUNT_NOTIFICATIONS):
        recipient = pick_one(ctx.all_internal)
        Notification.objects.create(
            recipient=recipient,
            actor=pick_one([u for u in ctx.all_internal if u != recipient]),
            verb=pick_one(verbs),
            unread=random.random() < 0.5,
        )

    # =====================================================================
    # 2. WorkflowInstance → WorkflowTask → ApprovalHistory
    #    任务节点与 BPMN UserTask 严格对应
    # =====================================================================
    from app_workflow.models import WorkflowInstance, WorkflowTask, ApprovalHistory

    wf_inst_count = 0
    for p in pick(ctx.projects, 5):
        wf_def = p.approval_workflow or pick_one(ctx.workflow_defs)
        bpmn_tasks = BPMN_TASK_MAP.get(wf_def.name, [])

        # 决定实例整体状态
        instance_status = pick_one(['RUNNING', 'COMPLETED', 'COMPLETED', 'COMPLETED'])

        instance = WorkflowInstance.objects.create(
            definition=wf_def,
            status=instance_status,
            started_by=pick_one(ctx.all_internal),
            completed_at=timezone.now() if instance_status == 'COMPLETED' else None,
        )
        wf_inst_count += 1

        # --- 为每个 BPMN UserTask 创建对应的 WorkflowTask ---
        if bpmn_tasks:
            # 根据实例状态决定任务推进到第几步
            if instance_status == 'COMPLETED':
                # 全部完成
                last_completed_idx = len(bpmn_tasks)
            else:
                # 进行中：随机停在某个步骤
                last_completed_idx = random.randint(0, len(bpmn_tasks) - 1)

            for j, (bpmn_id, task_name) in enumerate(bpmn_tasks):
                if j < last_completed_idx:
                    task_status = 'COMPLETED'
                    assignee = pick_one(ctx.all_internal)
                elif j == last_completed_idx and instance_status == 'RUNNING':
                    task_status = 'PENDING'
                    assignee = pick_one(ctx.all_internal)
                else:
                    task_status = 'PENDING'
                    assignee = None

                task = WorkflowTask.objects.create(
                    instance=instance,
                    task_name=task_name,
                    assigned_to=assignee,
                    status=task_status,
                    spiff_task_id=bpmn_id,  # 与 BPMN userTask id 一致
                )

                # 已完成任务 → 创建审批历史
                if task.status == 'COMPLETED':
                    ApprovalHistory.objects.create(
                        instance=instance,
                        task=task,
                        approver=task.assigned_to or pick_one(ctx.all_internal),
                        action=pick_one(['APPROVE', 'APPROVE', 'APPROVE', 'REJECT']),
                        remark="approved" if random.random() < 0.8 else "needs revision",
                    )
        else:
            # 没有 BPMN 任务映射的兜底：创建 1-3 个通用任务
            for j in range(random.randint(1, 3)):
                assignee = pick_one(ctx.all_internal)
                status = pick_one(['COMPLETED', 'COMPLETED', 'COMPLETED', 'PENDING'])
                task = WorkflowTask.objects.create(
                    instance=instance,
                    task_name=f"approval step {j + 1}",
                    assigned_to=assignee,
                    status=status,
                    spiff_task_id=f"task_{instance.id}_{j}",
                )
                if task.status == 'COMPLETED':
                    ApprovalHistory.objects.create(
                        instance=instance,
                        task=task,
                        approver=task.assigned_to or pick_one(ctx.all_internal),
                        action=pick_one(['APPROVE', 'APPROVE', 'APPROVE', 'REJECT']),
                        remark="approved" if random.random() < 0.8 else "needs revision",
                    )

        # --- 将审批实例关联到项目的活跃节点 ---
        active_nodes = [n for n in p.nodes.all() if n.status == 'DOING']
        if active_nodes:
            active_nodes[0].workflow_instance = instance
            active_nodes[0].status = 'AWAITING_APPROVAL'
            active_nodes[0].save()

    print(f"  notifications={COUNT_NOTIFICATIONS}, "
          f"workflow_instances={wf_inst_count}, "
          f"workflow_tasks={WorkflowTask.objects.count()}, "
          f"approval_history={ApprovalHistory.objects.count()}")
