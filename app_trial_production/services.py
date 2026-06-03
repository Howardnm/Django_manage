import logging
from app_workflow.services import WorkflowService
from app_workflow.models import WorkflowDefinition
from .models import ProductionOrder

logger = logging.getLogger(__name__)


class TrialProductionService:

    @staticmethod
    def start_workflow(order: ProductionOrder, definition: WorkflowDefinition, started_by):
        """为工单启动BPMN工作流"""
        if order.workflow_instance:
            logger.warning(f"Order {order.code} already has a workflow instance")
            return None

        has_color_matching = order.formula_details.filter(
            needs_color_matching=True).exists()
        context_data = {
            'needs_color_matching': has_color_matching,
            'order_code': order.code,
        }

        callback_config = {
            'handler': 'app_trial_production.workflow_handlers.handle_production_order_callback',
            'args': {'order_pk': order.pk},
        }

        instance = WorkflowService.start(
            definition=definition,
            started_by=started_by,
            related_object=order,
            context_data=context_data,
            callback_config=callback_config,
        )

        order.workflow_instance = instance
        order.status = 'WORKFLOW_RUNNING'
        order.save(update_fields=['workflow_instance', 'status'])
        return instance

    @staticmethod
    def write_back_results(testing_order):
        """将测试结果回写到配方"""
        from app_formula.models import FormulaTestResult, LabFormula

        order = testing_order
        production_order = order.production_order
        formulas = LabFormula.objects.filter(
            code=production_order.trial_code,
            project=production_order.project,
        )

        written = 0
        for trial_result in order.test_results.filter(is_written_back=False):
            if trial_result.value is not None or trial_result.value_text:
                for formula in formulas:
                    FormulaTestResult.objects.update_or_create(
                        formula=formula,
                        test_config=trial_result.test_config,
                        defaults={
                            'value': trial_result.value,
                            'value_text': trial_result.value_text,
                        },
                    )
                trial_result.is_written_back = True
                trial_result.save(update_fields=['is_written_back'])
                written += 1

        if written:
            order.status = 'RESULTS_WRITTEN_BACK'
            order.save(update_fields=['status'])

        return written
