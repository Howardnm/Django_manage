import logging
from django.db import transaction

from app_color_center.models import ColorMatchingTask
from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)

# 这两态还等配色员在编辑页保存。下发前填过的色粉不算已填写。
OPEN_COLOR_TASK_STATUSES = (
    ColorMatchingTask.Status.PENDING,
    ColorMatchingTask.Status.IN_PROGRESS,
)


def _bom_has_entries(bom):
    """有 prefetch 时用缓存，避免列表页一行一次查询。"""
    cache = getattr(bom, '_prefetched_objects_cache', None) or {}
    if 'entries' in cache:
        return bool(cache['entries'])
    return bom.entries.exists()


def color_bom_counts_as_filled(formula, task=None):
    """有明细，且不是未完成任务下发之前填的，才算已填写。

    没有任务，或任务已完成 / 无需配色：有明细即已填写。
    任务还在待配色或配色中：色粉 BOM 的更新时间早于任务创建时间，就还没确认。
    """
    bom = getattr(formula, 'color_powder_bom', None)
    if bom is None or not _bom_has_entries(bom):
        return False
    if (
        task is not None
        and task.status in OPEN_COLOR_TASK_STATUSES
        and bom.updated_at < task.created_at
    ):
        return False
    return True


def confirmed_color_formula_ids(formulas):
    """这批配方里，色粉 BOM 已经算填写完成的主键。"""
    formulas = list(formulas)
    if not formulas:
        return set()
    opened_at = {}
    rows = ColorMatchingTask.objects.filter(
        status__in=OPEN_COLOR_TASK_STATUSES,
        production_order__formula_details__needs_color_matching=True,
        production_order__formula_details__formula_id__in=[f.pk for f in formulas],
    ).values_list(
        'production_order__formula_details__formula_id',
        'created_at',
    )
    for formula_id, created_at in rows:
        previous = opened_at.get(formula_id)
        if previous is None or created_at > previous:
            opened_at[formula_id] = created_at
    confirmed = set()
    for formula in formulas:
        bom = getattr(formula, 'color_powder_bom', None)
        if bom is None or not _bom_has_entries(bom):
            continue
        task_at = opened_at.get(formula.pk)
        if task_at is not None and bom.updated_at < task_at:
            continue
        confirmed.add(formula.pk)
    return confirmed


def formula_has_open_color_task(formula):
    """这个配方还挂着未完成的配色任务。"""
    return ColorMatchingTask.objects.filter(
        status__in=OPEN_COLOR_TASK_STATUSES,
        production_order__formula_details__formula=formula,
        production_order__formula_details__needs_color_matching=True,
    ).exists()


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
