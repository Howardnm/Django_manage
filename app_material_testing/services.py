import logging
from django.db import transaction

from common_utils.state_machine import StateMachine

logger = logging.getLogger(__name__)


class TestingTaskService:
    """测试任务业务"""

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

        # 首次填写时自动转为测试中
        if task.status == 'PENDING':
            StateMachine.transition(task, 'IN_PROGRESS', user)

        logger.info(f"TestingTask {task.pk} results filled ({len(results_matrix)} entries)")

    @staticmethod
    @transaction.atomic
    def write_back_results(task):
        """
        将测试结果回写到 FormulaTestResult。

        Returns:
            int: 回写的结果条数
        """
        from app_formula.models import FormulaTestResult

        if task.status == 'RESULTS_WRITTEN_BACK':
            return 0

        written = 0
        for trial_result in task.test_results.filter(is_written_back=False):
            if (trial_result.value is not None or trial_result.value_text) and trial_result.formula:
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

        if written:
            if task.status != 'COMPLETED':
                StateMachine.transition(task, 'COMPLETED')
            StateMachine.transition(task, 'RESULTS_WRITTEN_BACK')

            # 检查是否可以完成工单
            from app_trial_production.services.order_service import ProductionOrderService
            ProductionOrderService.check_and_advance(task.production_order)

        logger.info(f"TestingTask {task.pk} wrote back {written} results")
        return written
