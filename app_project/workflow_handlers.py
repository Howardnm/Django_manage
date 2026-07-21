from django.utils import timezone
from app_workflow.models import WorkflowInstance
from app_project.models import ProjectNode
import logging

logger = logging.getLogger(__name__)

def handle_project_node_workflow_callback(instance: WorkflowInstance, target_status: str, **kwargs):
    """
    处理项目节点审批流程的回调函数。
    这个函数由 app_workflow 模块调用，用于在流程完成或驳回时更新 ProjectNode 的状态。

    :param instance: 流程实例对象
    :param target_status: 流程的最终状态 ('DONE', 'ROLLBACK' 或 'CANCELED')
    :param kwargs: 额外的回调参数，例如可以从 callback_config 中传递
    """
    node_pk = kwargs.get('node_pk')
    if not node_pk:
        logger.error(f"Callback for Workflow instance {instance.pk} missing 'node_pk' in kwargs.")
        return

    try:
        # 通过传递的 node_pk 重新获取 ProjectNode 对象，确保获取到最新状态
        obj = ProjectNode.objects.get(pk=node_pk)
    except ProjectNode.DoesNotExist:
        logger.error(f"ProjectNode with pk={node_pk} not found for workflow instance {instance.pk} callback.")
        return
    except Exception as e:
        logger.error(f"Error fetching ProjectNode with pk={node_pk} for workflow instance {instance.pk} callback: {e}", exc_info=True)
        return

    try:
        if target_status == 'DONE':
            obj.status = 'DONE'
            logger.info(f"ProjectNode {obj.pk} status updated to DONE by workflow {instance.pk}")
        elif target_status == 'ROLLBACK':
            obj.status = 'DOING'  # 驳回时，将节点状态改回"进行中"
            logger.info(f"ProjectNode {obj.pk} status updated to DOING (ROLLBACK) by workflow {instance.pk}")
        elif target_status == 'CANCELED':
            obj.status = 'DOING'  # 取消时，将节点状态改回"进行中"
            logger.info(f"ProjectNode {obj.pk} status updated to DOING (CANCELED) by workflow {instance.pk}")
        
        obj.save()
        logger.debug(f"ProjectNode {obj.pk} saved with new status {obj.status}")

    except Exception as e:
        logger.error(f"Error updating ProjectNode {obj.pk} from workflow {instance.pk} callback: {e}", exc_info=True)
        # 可以在这里添加更复杂的错误处理，例如记录到某个错误日志模型


def handle_project_change_callback(instance: WorkflowInstance, target_status: str, **kwargs):
    """
    处理项目信息编辑审批流程的回调函数。

    由 app_workflow 模块在工作流完成/驳回/取消时调用。

    :param instance: 流程实例对象
    :param target_status: 流程最终状态 ('DONE', 'ROLLBACK' 或 'CANCELED')
    :param kwargs: callback_config.args 中的参数，包含 change_id
    """
    change_id = kwargs.get('change_id')
    if not change_id:
        logger.error("Workflow callback missing 'change_id' in kwargs (instance=%s)",
                     instance.pk if instance else 'None')
        return

    from app_project.models import Project, ProjectFieldChange

    try:
        change = ProjectFieldChange.objects.select_related('project').get(pk=change_id)
    except ProjectFieldChange.DoesNotExist:
        logger.error(f"ProjectFieldChange pk={change_id} not found for workflow callback")
        return

    project = change.project

    try:
        if target_status == 'DONE':
            # 应用全部变更到项目实体
            project.code = change.code
            project.name = change.name
            project.grade = change.grade
            project.material = change.material
            project.description = change.description
            project.workflow_instance = None
            project.save()

            change.status = 'APPROVED'
            change.resolved_at = timezone.now()
            change.save(update_fields=['status', 'resolved_at'])

            logger.info("Project %s updated by workflow %s (DONE)", project.pk, instance.pk)

        elif target_status in ('ROLLBACK', 'CANCELED'):
            # 驳回/取消：清空活跃审批标记，变更记录标记为已拒绝
            project.workflow_instance = None
            project.save(update_fields=['workflow_instance'])

            change.status = 'REJECTED'
            change.resolved_at = timezone.now()
            change.save(update_fields=['status', 'resolved_at'])

            logger.info(
                "Project %s workflow %s %s -- pending changes discarded",
                project.pk, instance.pk, target_status,
            )

        else:
            logger.warning(
                "Unknown target_status '%s' for workflow %s callback, clearing workflow_instance",
                target_status, instance.pk,
            )
            project.workflow_instance = None
            project.save(update_fields=['workflow_instance'])

    except Exception:
        logger.error(
            "Error in project change workflow callback: instance=%s change=%s target_status=%s",
            instance.pk, change_id, target_status,
            exc_info=True,
        )
