import logging
from django.db import transaction

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


def check_order_bom_complete(order):
    """检查工单中所有 needs_color_matching=True 的配方是否都有色粉 BOM 条目"""
    from app_formula.models import ColorPowderBOM
    for fd in order.formula_details.filter(needs_color_matching=True):
        bom = ColorPowderBOM.objects.filter(formula_id=fd.formula_id).first()
        if not bom or not bom.entries.exists():
            return False
    return True


@transaction.atomic
def batch_copy_bom(source_formula, target_trial_code, user, overwrite=False,
                   production_order_id=None):
    """将当前配方的色粉 BOM 批量复制到同实验单号下其他需要配色的配方。

    Args:
        overwrite: False=跳过已有BOM的配方，True=强制覆盖已有BOM
        production_order_id: 限定目标工单范围（可选）。传入后只复制到该工单关联的配方。
    """
    from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry
    from app_trial_production.models import ProductionOrderFormulaDetail

    source_bom = getattr(source_formula, 'color_powder_bom', None)
    if not source_bom or not source_bom.entries.exists():
        return 0

    # 同实验单号下需要配色的配方版本（可限定工单范围）
    formula_ids_qs = ProductionOrderFormulaDetail.objects.filter(
        formula__code=target_trial_code,
        needs_color_matching=True,
    ).exclude(formula_id=source_formula.pk)

    if production_order_id:
        formula_ids_qs = formula_ids_qs.filter(
            production_order_id=production_order_id
        )

    formula_ids = formula_ids_qs.values_list('formula_id', flat=True).distinct()

    copied = 0
    source_entries = list(source_bom.entries.all())
    for fid in formula_ids:
        if not overwrite:
            target_bom = ColorPowderBOM.objects.filter(formula_id=fid).first()
            if target_bom and target_bom.entries.exists():
                continue  # 非覆盖模式：跳过已有 BOM

        target_bom, _ = ColorPowderBOM.objects.get_or_create(formula_id=fid)
        target_bom.filled_by = user
        target_bom.entries.all().delete()  # 清空后重填
        for entry in source_entries:
            ColorPowderBOMEntry.objects.create(
                color_powder_bom=target_bom,
                feeding_port=entry.feeding_port,
                weighing_scale=entry.weighing_scale,
                raw_material=entry.raw_material,
                percentage=entry.percentage,
                is_pre_mix=entry.is_pre_mix,
                pre_mix_order=entry.pre_mix_order,
                pre_mix_time=entry.pre_mix_time,
            )
        target_bom.save()
        copied += 1

    if copied:
        logger.info(
            f"Batch copied BOM from formula {source_formula.pk} "
            f"to {copied} formulas under trial_code {target_trial_code}"
        )
    return copied


class ColorMatchingTaskService:
    """配色任务业务"""

    @staticmethod
    @transaction.atomic
    def start_task(task, user):
        """开始配色任务"""
        if not task.operator_id:
            task.operator = user
            task.save(update_fields=['operator'])
        StateMachine.transition(task, 'IN_PROGRESS', user)

    @staticmethod
    def mark_not_required(task):
        """标记无需配色"""
        StateMachine.transition(task, 'NOT_REQUIRED')

    @staticmethod
    @transaction.atomic
    def complete_task(task, user):
        """
        完成配色任务 → 调用并行屏障检查。
        配色数据本身已保存在 app_formula.ColorPowderBOM 中。
        如果任务仍在 PENDING 或 NOT_REQUIRED 状态，自动先转为 IN_PROGRESS。
        """
        if task.status in ('PENDING', 'NOT_REQUIRED'):
            if not task.operator_id:
                task.operator = user
                task.save(update_fields=['operator'])
            StateMachine.transition(task, 'IN_PROGRESS', user)

        StateMachine.transition(task, 'COMPLETED', user)

        # 检查并行屏障（挤出+配色均完成 → 推进工单）
        from app_trial_production.services.order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(task.production_order)
