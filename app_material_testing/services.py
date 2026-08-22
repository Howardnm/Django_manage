import logging

from django.db import transaction
from django.db.models import Q

from common_utils.state_machine import StateMachine
from app_material_testing.models import TestingTask

logger = logging.getLogger(__name__)


class TestingTaskService:
    """测试任务业务"""

    @staticmethod
    def _is_complete(task):
        """判定「所有 test_item × formula 单元格是否都已填值」。

        一个单元格有值 = value 非空 或 value_text 非空。
        空矩阵（无测试项或无配方）视为未完整，避免空任务误转 COMPLETED。
        """
        from app_formula.models import LabFormula
        order = task.production_order
        config_ids = set(task.test_items.values_list('pk', flat=True))
        formula_ids = set(LabFormula.objects.filter(
            code=order.trial_code, project=order.project,
        ).values_list('pk', flat=True))
        if not config_ids or not formula_ids:
            return False

        filled = set(
            task.test_results
            .filter(test_config_id__in=config_ids, formula_id__in=formula_ids)
            .filter(Q(value__isnull=False) | ~Q(value_text=''))
            .values_list('test_config_id', 'formula_id'),
        )
        expected = {(c, f) for c in config_ids for f in formula_ids}
        return filled >= expected

    @staticmethod
    @transaction.atomic
    def fill_results(task, results_matrix, user=None):
        """
        填写测试结果矩阵。

        Args:
            task: TestingTask 实例
            results_matrix: list of dict {
                test_config_id, formula_id,
                value, value_text, test_date, remark
            }
            user: 测试员
        """
        from app_material_testing.models import TrialTestResult

        for entry in results_matrix:
            result, _ = TrialTestResult.objects.get_or_create(
                testing_task=task,
                test_config_id=entry['test_config_id'],
                formula_id=entry['formula_id'],
            )
            result.value = entry.get('value')
            result.value_text = entry.get('value_text', '')
            result.test_date = entry.get('test_date')
            result.remark = entry.get('remark', '')
            result.save()

        # 终态不可改（view 层已守卫，此处防御性不推进）
        if task.status == TestingTask.Status.RESULTS_WRITTEN_BACK:
            return

        complete = TestingTaskService._is_complete(task)
        if complete:
            if task.status == TestingTask.Status.PENDING:
                StateMachine.transition(task, TestingTask.Status.IN_PROGRESS, user)
            if task.status == TestingTask.Status.IN_PROGRESS:
                StateMachine.transition(task, TestingTask.Status.COMPLETED, user)
        else:
            if task.status == TestingTask.Status.PENDING:
                StateMachine.transition(task, TestingTask.Status.IN_PROGRESS, user)
            elif task.status == TestingTask.Status.COMPLETED:
                # 完整后又改动导致不完整 → 退回测试中
                StateMachine.transition(task, TestingTask.Status.IN_PROGRESS, user)
            # task.status == IN_PROGRESS → 保持

        logger.info(f"TestingTask {task.pk} results filled ({len(results_matrix)} entries)")

    @staticmethod
    def _write_back_entries(task):
        """覆盖回写所有有值条目到 FormulaTestResult，标记 is_written_back。

        Returns: 本次实际覆盖到配方库的有值条目数。
        """
        from app_formula.models import FormulaTestResult

        written = 0
        for trial_result in task.test_results.all():
            if (trial_result.value is not None or trial_result.value_text) and trial_result.formula:
                existing = FormulaTestResult.objects.filter(
                    formula=trial_result.formula,
                    test_config=trial_result.test_config,
                    production_order=task.production_order,
                ).first()
                if existing and (
                    existing.value != trial_result.value
                    or existing.value_text != trial_result.value_text
                ):
                    logger.info(
                        f"[write_back] Overwriting FormulaTestResult: "
                        f"formula_id={trial_result.formula_id}, "
                        f"test_config={trial_result.test_config.name}, "
                        f"order={task.production_order.code}, "
                        f"old=({existing.value}, '{existing.value_text}'), "
                        f"new=({trial_result.value}, '{trial_result.value_text}')"
                    )

                FormulaTestResult.objects.update_or_create(
                    formula=trial_result.formula,
                    test_config=trial_result.test_config,
                    production_order=task.production_order,
                    defaults={
                        'value': trial_result.value,
                        'value_text': trial_result.value_text,
                    },
                )
                trial_result.is_written_back = True
                trial_result.save(update_fields=['is_written_back'])
                written += 1
        return written

    @staticmethod
    def _consume_specimens_and_advance(task):
        """标记工单待测试样条为已消耗，并检查工单推进。"""
        from app_trial_production.models import SampleInventory
        from django.utils import timezone as tz

        consumed = SampleInventory.objects.filter(
            production_order=task.production_order,
            type='SPECIMEN',
            sub_type='FOR_TESTING',
            status='IN_LAB',
        ).update(status='CONSUMED', updated_at=tz.now())
        if consumed:
            logger.info(
                f"Marked {consumed} specimens as CONSUMED "
                f"for order {task.production_order.code}"
            )

        from app_trial_production.services.order_service import ProductionOrderService
        ProductionOrderService.check_and_advance(task.production_order)

    @staticmethod
    @transaction.atomic
    def write_back_results(task):
        """
        将测试结果回写到 FormulaTestResult（可覆盖）。

        仅当数据填写完整且本次有值条目回写时才推进到终态 RESULTS_WRITTEN_BACK；
        未完整时仅覆盖回写、不推进状态，允许后续继续填写/回写。

        Returns:
            int: 本次实际覆盖到配方库的有值条目数
        """
        if task.status == TestingTask.Status.RESULTS_WRITTEN_BACK:
            return 0

        written = TestingTaskService._write_back_entries(task)
        complete = TestingTaskService._is_complete(task)

        if written and complete:
            if task.status == TestingTask.Status.PENDING:
                StateMachine.transition(task, TestingTask.Status.IN_PROGRESS)
            if task.status == TestingTask.Status.IN_PROGRESS:
                StateMachine.transition(task, TestingTask.Status.COMPLETED)
            StateMachine.transition(task, TestingTask.Status.RESULTS_WRITTEN_BACK)
            TestingTaskService._consume_specimens_and_advance(task)

        logger.info(f"TestingTask {task.pk} wrote back {written} results")
        return written

    @staticmethod
    @transaction.atomic
    def force_complete_and_writeback(task):
        """
        手动过掉：覆盖回写所有有值条目并强制推进到终态，不做完整性校验。

        供测试员手动结束数据缺失的任务，复用同一套回写 + 样条消耗 + 工单推进逻辑。

        Returns:
            int: 本次覆盖到配方库的有值条目数（终态则 0）
        """
        if task.status == TestingTask.Status.RESULTS_WRITTEN_BACK:
            return 0

        written = TestingTaskService._write_back_entries(task)
        # 按状态机链条逐步补齐到终态（PENDING→IN_PROGRESS→COMPLETED→RESULTS_WRITTEN_BACK）
        if task.status == TestingTask.Status.PENDING:
            StateMachine.transition(task, TestingTask.Status.IN_PROGRESS)
        if task.status == TestingTask.Status.IN_PROGRESS:
            StateMachine.transition(task, TestingTask.Status.COMPLETED)
        StateMachine.transition(task, TestingTask.Status.RESULTS_WRITTEN_BACK)
        TestingTaskService._consume_specimens_and_advance(task)

        logger.info(f"TestingTask {task.pk} force completed, wrote back {written} results")
        return written