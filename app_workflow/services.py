import logging
from django.db import transaction
from django.utils import timezone
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.bpmn.specs.defaults import UserTask
from SpiffWorkflow.util.task import TaskState
from .models import WorkflowDefinition, WorkflowInstance, WorkflowTask, ApprovalHistory
from .engine import WorkflowEngine
from .signals import workflow_started, task_created, task_completed, workflow_completed, task_returned
from .exceptions import (TaskNotFoundError, CancelNotAllowedError, InvalidActionError,
                         ReturnNotAllowedError)

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
            # 从 extra_data 中剥离 step_form_data，避免大表单数据膨胀 workflow 状态
            engine_extra = {k: v for k, v in (extra_data or {}).items()
                            if k != 'step_form_data'}
            is_completed = engine.complete(
                workflow, spiff_task, action,
                extra_data={'remark': remark, **engine_extra},
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

            # 合并分步表单数据 → FormSubmission.form_data
            step_form_data = (extra_data or {}).get('step_form_data')
            if step_form_data and instance.content_object:
                from app_form_management.models import FormSubmission
                related = instance.content_object
                if isinstance(related, FormSubmission):
                    merged = dict(related.form_data or {})
                    merged.update(step_form_data)
                    related.form_data = merged
                    related.save(update_fields=['form_data'])

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

    # ── 退回 ──────────────────────────────────────────────────

    @staticmethod
    def return_task(task: WorkflowTask, user, target_task, remark: str = '',
                    extra_data: dict = None) -> WorkflowInstance:
        """将当前任务退回给指定前序节点。
        target_task: WorkflowTask 实例（退回到审批节点）或 WorkflowTask 实例（退回到发起人）
        退回发起人时传入 is_initiator=True 标记。
        """
        instance = task.instance
        is_initiator_target = isinstance(target_task, dict) and target_task.get('is_initiator')

        # 1. 校验
        if task.status != 'PENDING':
            raise InvalidActionError("只能退回待处理的任务")
        if task.assigned_to and task.assigned_to != user:
            raise InvalidActionError("您不是该任务的负责人，无法退回")

        if not is_initiator_target:
            if target_task.instance_id != instance.id:
                raise ReturnNotAllowedError("退回目标任务不属于同一流程实例")
            if target_task.created_at >= task.created_at:
                raise ReturnNotAllowedError("只能退回到前序节点")
            if target_task.status not in ('COMPLETED', 'RETURNED'):
                raise ReturnNotAllowedError("退回目标任务必须处于已完成状态")

        engine = WorkflowEngine(instance.definition)

        with transaction.atomic():
            # 2. 合并当前步骤的表单数据（如有）
            step_form_data = (extra_data or {}).get('step_form_data')
            if step_form_data and instance.content_object:
                from app_form_management.models import FormSubmission
                related = instance.content_object
                if isinstance(related, FormSubmission):
                    merged = dict(related.form_data or {})
                    merged.update(step_form_data)
                    related.form_data = merged
                    related.save(update_fields=['form_data'])

            if is_initiator_target:
                # 退回到发起人：取消所有待处理任务，标记需要发起人重新填写
                WorkflowTask.objects.filter(instance=instance, status='PENDING').update(
                    status='CANCELED')
                task.status = 'RETURNED'
                task.remark = remark
                task.completed_at = timezone.now()
                task.save()

                # 标记需要发起人修订，不创建 BPMN 任务
                ctx = dict(instance.context_data or {})
                ctx['_need_revision'] = True
                instance.context_data = ctx
                instance.spiff_workflow_data = {}  # 清空，提交时重建

                # 记录历史
                ApprovalHistory.objects.create(
                    instance=instance,
                    task=task,
                    approver=user,
                    action='RETURN',
                    remark=remark or '退回到发起人（重新填写）',
                )
            else:
                # 退回到前序审批节点
                workflow = engine.deserialize(instance.spiff_workflow_data)

                # 查找 Spiff 任务
                spiff_task = None
                if task.spiff_instance_id:
                    try:
                        spiff_task = workflow.get_task_from_id(int(task.spiff_instance_id))
                    except Exception:
                        pass
                if not spiff_task:
                    for st in engine.get_ready_user_tasks(workflow):
                        st_bpmn_id = getattr(st.task_spec, 'bpmn_id',
                                             getattr(st.task_spec, 'id', None))
                        if isinstance(st.task_spec, UserTask) and str(st_bpmn_id) == task.spiff_task_id:
                            spiff_task = st
                            break
                if not spiff_task:
                    raise TaskNotFoundError("未找到可退回的待处理任务")

                # 引擎回退
                engine.return_to_task(workflow, spiff_task, target_task.spiff_task_id)

                # 当前任务标记为 RETURNED
                task.status = 'RETURNED'
                task.remark = remark
                task.completed_at = timezone.now()
                task.save()

                # 删除目标任务之后、当前任务之间的 PENDING 任务
                WorkflowTask.objects.filter(
                    instance=instance,
                    created_at__gt=target_task.created_at,
                    status='PENDING',
                ).update(status='CANCELED')

                # 序列化引擎状态
                instance.spiff_workflow_data = engine.serialize(workflow)

                # 记录历史
                ApprovalHistory.objects.create(
                    instance=instance,
                    task=task,
                    return_target_task=target_task,
                    approver=user,
                    action='RETURN',
                    remark=remark or f'退回到 {target_task.task_name}',
                )

            instance.save()

            # 同步新任务（退回发起人时不创建 BPMN 任务）
            if not is_initiator_target:
                WorkflowService.sync_tasks(instance, workflow, engine)

            # 信号
            task_returned.send(sender=WorkflowService, task=task, user=user,
                               target_task=target_task if not is_initiator_target else None)

            return instance

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
                camunda_cache = workflow.data.get('_camunda_assignments', {})
                camunda_info = camunda_cache.get(st_bpmn_id, {})
                form_step = camunda_info.get('form_step')
                workflow_task = WorkflowTask.objects.create(
                    instance=instance,
                    task_name=st.task_spec.name or st_bpmn_id,
                    assigned_to=assigned_to_user,
                    spiff_task_id=st_bpmn_id,
                    spiff_instance_id=str(st.id),
                    status='PENDING',
                    candidate_groups=candidate_groups_list,
                    form_step=form_step,
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
