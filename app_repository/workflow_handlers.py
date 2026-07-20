import logging
from django.utils import timezone
from app_workflow.models import WorkflowInstance

logger = logging.getLogger(__name__)


def handle_repo_change_callback(instance: WorkflowInstance, target_status: str, **kwargs):
    """
    处理项目档案变更审批流程的回调函数。

    由 app_workflow 模块在工作流完成/驳回/取消时调用。

    :param instance: 流程实例对象
    :param target_status: 流程最终状态 ('DONE', 'ROLLBACK' 或 'CANCELED')
    :param kwargs: callback_config.args 中的参数，包含 change_id
    """
    change_id = kwargs.get('change_id')
    if not change_id:
        logger.error("Workflow callback missing 'change_id' in kwargs (instance=%s)", instance.pk if instance else 'None')
        return

    from app_repository.models import ProjectRepository, ProjectRepositoryFieldChange

    try:
        change = ProjectRepositoryFieldChange.objects.select_related('repository').get(pk=change_id)
    except ProjectRepositoryFieldChange.DoesNotExist:
        logger.error(f"ProjectRepositoryFieldChange pk={change_id} not found for workflow callback")
        return

    repo = change.repository

    try:
        if target_status == 'DONE':
            # 应用全部变更到仓库实体
            repo.customer = change.customer
            repo.oem = change.oem
            repo.salesperson = change.salesperson
            repo.product_name = change.product_name
            repo.product_code = change.product_code
            repo.target_cost = change.target_cost
            repo.competitor_price = change.competitor_price
            repo.estimated_order_volume = change.estimated_order_volume
            repo.workflow_instance = None
            repo.save()

            change.status = 'APPROVED'
            change.resolved_at = timezone.now()
            change.save(update_fields=['status', 'resolved_at'])

            logger.info("ProjectRepository %s updated by workflow %s (DONE)", repo.pk, instance.pk)

        elif target_status in ('ROLLBACK', 'CANCELED'):
            # 驳回/取消：清空活跃审批标记，变更记录标记为已拒绝
            repo.workflow_instance = None
            repo.save(update_fields=['workflow_instance'])

            change.status = 'REJECTED'
            change.resolved_at = timezone.now()
            change.save(update_fields=['status', 'resolved_at'])

            logger.info(
                "ProjectRepository %s workflow %s %s — pending changes discarded",
                repo.pk, instance.pk, target_status,
            )

        else:
            logger.warning(
                "Unknown target_status '%s' for workflow %s callback, clearing workflow_instance",
                target_status, instance.pk,
            )
            repo.workflow_instance = None
            repo.save(update_fields=['workflow_instance'])

    except Exception:
        logger.error(
            "Error in repository workflow callback: instance=%s change=%s target_status=%s",
            instance.pk, change_id, target_status,
            exc_info=True,
        )
