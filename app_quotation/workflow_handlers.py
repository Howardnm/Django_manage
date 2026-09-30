"""
产品报价需求单审批流回调 handler。

由 WorkflowService._callback 动态 import 并调用，参数固定为
(instance, target_status, **callback_config['args'])。
"""

import logging

from .models import QuotationRequest

logger = logging.getLogger(__name__)


def handle_quotation_callback(instance, target_status, **kwargs):
    """审批流结束时更新需求单状态。

    target_status ∈ DONE / ROLLBACK / CANCELED。
    """
    request_pk = kwargs.get('request_pk')
    request = QuotationRequest.objects.filter(pk=request_pk).first()
    if request is None:
        logger.warning("报价需求单回调：未找到需求单 pk=%s", request_pk)
        return

    if target_status == 'DONE':
        request.status = QuotationRequest.Status.COMPLETED
    elif target_status == 'ROLLBACK':
        request.status = QuotationRequest.Status.REJECTED
    elif target_status == 'CANCELED':
        request.status = QuotationRequest.Status.CANCELED
    request.save(update_fields=['status'])
