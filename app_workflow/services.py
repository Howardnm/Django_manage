import logging
from django.db import transaction
from django.utils import timezone
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.bpmn.specs.defaults import UserTask
from SpiffWorkflow.util.task import TaskState
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory
from .engine import WorkflowEngine
from .signals import workflow_started, task_created, task_completed, workflow_completed
from .exceptions import TaskNotFoundError, CancelNotAllowedError, InvalidActionError

logger = logging.getLogger(__name__)


class WorkflowService:
    """工作流服务编排层: 协调引擎 + DB + 信号 + 回调"""

    # ── 启动 ──────────────────────────────────────────────────

    @staticmethod
    def start(definition: WorkflowDefinition, started_by,
              related_object=None, context_data: dict | None = None,
              callback_config: dict | None = None) -> WorkflowInstance:
        """启动流程实例"""
        if context_data is None:
            context_data = {}
        if callback_config is None:
            callback_config = {}

        engine = WorkflowEngine(definition)
        workflow = engine.create_workflow(context_data)
        workflow_data = engine.serialize(workflow)

        with transaction.atomic():
            instance = WorkflowInstance.objects.create(
                definition=definition,
                started_by=started_by,
                context_data=context_data,
                spiff_workflow_data=workflow_data,
                content_object=related_object,
                callback_config=callback_config,
            )
            ApprovalHistory.objects.create(
                instance=instance,
                approver=started_by,
                action='START',
                remark="启动流程",
            )
            WorkflowService.sync_tasks(instance, workflow, engine)
            workflow_started.send(sender=WorkflowService, instance=instance)

        return instance

    # ── 审批 ──────────────────────────────────────────────────

    @staticmethod
    def complete_task(task: WorkflowTask, user, action: str, remark: str = None,
                      extra_data: dict | None = None) -> WorkflowInstance:
        """处理审批任务: 引擎推进 + DB 更新 + 信号 + 回调"""
        instance = task.instance
        engine = WorkflowEngine(instance.definition)
        workflow = engine.deserialize(instance.spiff_workflow_data)

        # 查找 Spiff 任务实例
        spiff_task = None
        if task.spiff_instance_id:
            try:
                spiff_task = workflow.get_task_from_id(int(task.spiff_instance_id))
            except Exception:
                logger.warning(
                    f"WorkflowTask {task.pk} spiff_instance_id={task.spiff_instance_id} "
                    f"not found, falling back to spiff_task_id."
                )

        if not spiff_task:
            for st in engine.get_ready_user_tasks(workflow):
                st_bpmn_id = getattr(st.task_spec, 'bpmn_id',
                                     getattr(st.task_spec, 'id', None))
                if isinstance(st.task_spec, UserTask) and str(st_bpmn_id) == task.spiff_task_id:
                    spiff_task = st
                    break

        if not spiff_task:
            raise TaskNotFoundError("未找到匹配的可执行任务或任务已处理")

        with transaction.atomic():
            is_completed = engine.complete(
                workflow, spiff_task, action,
                extra_data={'remark': remark, **(extra_data or {})},
            )

            task.status = 'COMPLETED' if action == 'APPROVE' else 'REJECTED'
            task.remark = remark
            task.completed_at = timezone.now()
            task.save()

            ApprovalHistory.objects.create(
                instance=instance,
                task=task,
                approver=user,
                action='APPROVE' if action == 'APPROVE' else 'REJECT',
                remark=remark,
            )

            instance.spiff_workflow_data = engine.serialize(workflow)

            workflow_completed_status = None
            if action == 'REJECT':
                instance.status = 'REJECTED'
                instance.completed_at = timezone.now()
                WorkflowService._callback(instance, 'ROLLBACK')
                workflow_completed_status = 'REJECTED'
            elif is_completed:
                instance.status = 'COMPLETED'
                instance.completed_at = timezone.now()
                WorkflowService._callback(instance, 'DONE')
                workflow_completed_status = 'COMPLETED'

            instance.save()

            task_completed.send(sender=WorkflowService, task=task, user=user, action=action)

            if workflow_completed_status:
                workflow_completed.send(
                    sender=WorkflowService, instance=instance,
                    status=workflow_completed_status,
                )

            if instance.status == 'RUNNING':
                WorkflowService.sync_tasks(instance, workflow, engine)

            return instance

    # ── 取消 ──────────────────────────────────────────────────

    @staticmethod
    def cancel(instance: WorkflowInstance, user, reason: str = ""):
        """取消流程实例, 终止所有待处理任务"""
        if instance.status != 'RUNNING':
            raise CancelNotAllowedError("流程已结束, 无法取消")

        with transaction.atomic():
            instance.status = 'CANCELED'
            instance.completed_at = timezone.now()
            instance.canceled_by = user
            instance.cancel_reason = reason
            instance.save()

            instance.tasks.filter(status='PENDING').update(status='CANCELED')

            ApprovalHistory.objects.create(
                instance=instance,
                approver=user,
                action='CANCEL',
                remark=f"取消流程: {reason}" if reason else "取消流程",
            )

            WorkflowService._callback(instance, 'CANCELED')
            workflow_completed.send(
                sender=WorkflowService, instance=instance, status='CANCELED',
            )

    # ── 签收 / 转交 ───────────────────────────────────────────

    @staticmethod
    def claim(task: WorkflowTask, user):
        """签收候选任务"""
        if task.assigned_to is not None:
            raise InvalidActionError("任务已被签收")

        user_groups = set(user.review_groups.filter(
            is_active=True
        ).values_list('name', flat=True))
        is_candidate = (
            task.candidate_users.filter(pk=user.pk).exists()
            or any(g in task.candidate_groups for g in user_groups)
        )
        if not is_candidate:
            raise InvalidActionError("您不是该任务的候选人, 无法签收")

        task.assigned_to = user
        task.save(update_fields=['assigned_to'])

    @staticmethod
    def reassign(task: WorkflowTask, from_user, to_user):
        """转交任务给其他用户"""
        if task.assigned_to != from_user:
            raise InvalidActionError("任务不属于当前用户, 无法转交")
        task.assigned_to = to_user
        task.save(update_fields=['assigned_to'])

    # ── 同步 ──────────────────────────────────────────────────

    @staticmethod
    def sync_tasks(instance: WorkflowInstance, workflow: BpmnWorkflow,
                   engine: WorkflowEngine):
        """同步 Spiff 内部 Task → Django WorkflowTask 模型"""
        ready_tasks = workflow.get_tasks(state=TaskState.READY)
        for st in ready_tasks:
            if not isinstance(st.task_spec, UserTask):
                continue
            st_bpmn_id = getattr(st.task_spec, 'bpmn_id',
                                 getattr(st.task_spec, 'id', None))
            if not st_bpmn_id:
                continue

            workflow_task = WorkflowTask.objects.filter(
                instance=instance, spiff_instance_id=str(st.id),
            ).first()

            if not workflow_task:
                assigned_to_user, candidate_users_list, candidate_groups_list = (
                    engine.resolve_assignee(st, workflow, instance)
                )
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
                task_created.send(sender=WorkflowService, task=workflow_task)
            else:
                if workflow_task.status != 'PENDING':
                    workflow_task.status = 'PENDING'
                    workflow_task.save(update_fields=['status'])

    # ── 回调 ──────────────────────────────────────────────────

    @staticmethod
    def _callback(instance: WorkflowInstance, target_status: str):
        """回调业务模块的处理函数"""
        callback_config = instance.callback_config
        handler_path = callback_config.get('handler')
        if not handler_path:
            return

        import importlib
        try:
            module_name, func_name = handler_path.rsplit('.', 1)
            module = importlib.import_module(module_name)
            handler_func = getattr(module, func_name)
            handler_func(
                instance=instance, target_status=target_status,
                **callback_config.get('args', {}),
            )
        except Exception:
            logger.error(
                f"Workflow callback error: handler={handler_path} "
                f"instance={instance.pk} target_status={target_status}",
                exc_info=True,
            )
