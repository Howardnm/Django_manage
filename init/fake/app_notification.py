"""
app_notification 伪数据生成器

业务逻辑：
  - Notification：站内通知，包含 recipient(接收方) / actor(操作方) / verb(动作描述) / unread
  - 审批实例：为部分项目创建 WorkflowInstance → WorkflowTask → ApprovalHistory
    遵循审批流程：发起 → 审批通过/驳回，关联到项目的活跃节点
"""

import random
from django.db import transaction
from django.utils import timezone
from ._base import FakeContext, fake, pick_one, pick, COUNT_NOTIFICATIONS


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[13/13] Creating notifications & approval instances...")

    # --- Notification ---
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

    # --- 审批实例（需要在项目创建之后） ---
    from app_workflow.models import WorkflowInstance, WorkflowTask, ApprovalHistory

    wf_inst_count = 0
    for p in pick(ctx.projects, 5):
        wf_def = p.approval_workflow or pick_one(ctx.workflow_defs)
        instance = WorkflowInstance.objects.create(
            definition=wf_def,
            status=pick_one(['RUNNING', 'COMPLETED', 'COMPLETED', 'COMPLETED']),
            started_by=pick_one(ctx.all_internal),
            completed_at=timezone.now() if random.random() < 0.6 else None,
        )
        wf_inst_count += 1
        # 创建审批任务
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

        # 将审批实例关联到项目的活跃节点
        active_nodes = [n for n in p.nodes.all() if n.status == 'DOING']
        if active_nodes:
            active_nodes[0].workflow_instance = instance
            active_nodes[0].status = 'AWAITING_APPROVAL'
            active_nodes[0].save()

    print(f"  notifications={COUNT_NOTIFICATIONS}, "
          f"workflow_instances={wf_inst_count}, "
          f"workflow_tasks={WorkflowTask.objects.count()}, "
          f"approval_history={ApprovalHistory.objects.count()}")
