import logging
from app_workflow.models import WorkflowInstance

logger = logging.getLogger(__name__)


def handle_production_order_callback(instance: WorkflowInstance, target_status: str, **kwargs):
    """
    处理生产工单工作流的完成/驳回/取消回调。
    - DONE → ACCEPTED（接单）
    - ROLLBACK → DRAFT
    - CANCELED → CANCELED
    """
    from app_trial_production.models import ProductionOrder
    from app_trial_production.services import ProductionOrderService, StateMachine

    order_pk = kwargs.get('order_pk')
    if not order_pk:
        logger.error("ProductionOrder workflow callback missing order_pk")
        return

    try:
        order = ProductionOrder.objects.get(pk=order_pk)
    except ProductionOrder.DoesNotExist:
        logger.error(f"ProductionOrder pk={order_pk} not found in workflow callback")
        return

    if target_status == 'DONE':
        # 审批通过 → 接单，自动创建挤出+配色任务
        try:
            ProductionOrderService.accept_order(order)
        except Exception:
            logger.exception(f"Failed to accept order {order.code} in workflow callback")
    elif target_status == 'ROLLBACK':
        StateMachine.transition(order, 'DRAFT')
    elif target_status == 'CANCELED':
        StateMachine.transition(order, 'CANCELED')

    logger.info(f"ProductionOrder {order.code} workflow callback: {target_status}")
