"""
产品报价需求单信号处理 — 审批人解析。

task_created：审批流每创建一个待办任务时，按需求单累积状态解析审批人并覆盖 assigned_to。
（app_workflow 自带的 resolve_assignee 只按发起人 org 解析，无法按「选定业务组别/分基地/
②最终经办人」解析，故在此统一收口、不改 app_workflow。）
"""

import logging

from django.dispatch import receiver

from app_workflow.signals import task_created

from .models import QuotationRequest
from .services import resolve_assignee

logger = logging.getLogger(__name__)


@receiver(task_created)
def resolve_quotation_task_assignee(sender, task, **kwargs):
    """为报价需求单流程的待办任务解析审批人。"""
    request = task.instance.content_object
    if not isinstance(request, QuotationRequest):
        return

    resolved = resolve_assignee(request, task.spiff_task_id)
    if resolved is None:
        logger.warning(
            "报价需求单 %s 任务 %s 未解析到审批人，保留默认指派",
            request.code, task.spiff_task_id,
        )
        return
    if task.assigned_to_id != resolved.pk:
        task.assigned_to = resolved
        task.save(update_fields=['assigned_to'])
