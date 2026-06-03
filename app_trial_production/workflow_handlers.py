import logging
from app_workflow.models import WorkflowInstance

logger = logging.getLogger(__name__)


def handle_production_order_callback(instance: WorkflowInstance, target_status: str, **kwargs):
    """处理生产工单工作流的完成/驳回/取消回调"""
    from app_trial_production.models import ProductionOrder

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
        order.status = 'EXTRUDING'
    elif target_status == 'ROLLBACK':
        order.status = 'DRAFT'
    elif target_status == 'CANCELED':
        order.status = 'CANCELED'

    order.save(update_fields=['status'])
    logger.info(f"ProductionOrder {order.code} workflow callback: {target_status}")
