from django import forms
from django.core.exceptions import ValidationError
from common_utils.filters import TablerFormMixin


class TestResultMatrixForm(TablerFormMixin, forms.Form):
    """
    测试结果矩阵表单 — 校验 POST 数据中的 test_config_id / formula_id
    是否属于当前 TestingTask 对应的工单，以及数据类型是否匹配。
    """

    def __init__(self, *args, testing_task=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.testing_task = testing_task
        if not testing_task:
            return

        # 预取合法 ID 集合，避免 clean() 中重复查库
        self._valid_test_item_ids = set(
            testing_task.test_items.values_list('pk', flat=True)
        )
        self._test_configs = {
            tc.pk: tc
            for tc in testing_task.test_items.all()
        }

        from app_formula.models import LabFormula
        order = testing_task.production_order
        self._valid_formula_ids = set(
            LabFormula.objects.filter(
                code=order.trial_code,
                project=order.project,
            ).values_list('pk', flat=True)
        )

    def clean(self):
        cleaned = super().clean()
        if not self.testing_task:
            raise ValidationError('缺少关联测试任务')

        results = []
        errors = []

        # 扫描 POST 数据中所有的 value_{test_config_id}_{formula_id} 键
        for key in self.data:
            if not key.startswith('value_'):
                continue
            parts = key.split('_', 2)  # ['value', 'testConfigPk', 'formulaPk']
            if len(parts) < 3:
                continue
            try:
                tc_id = int(parts[1])
                f_id = int(parts[2])
            except (ValueError, TypeError):
                errors.append(ValidationError(f'无效的字段名格式: {key}'))
                continue

            if tc_id not in self._valid_test_item_ids:
                errors.append(ValidationError(
                    f'测试项目 ID={tc_id} 不属于当前测试任务'
                ))
                continue

            if f_id not in self._valid_formula_ids:
                errors.append(ValidationError(
                    f'配方 ID={f_id} 不属于当前工单的实验单号'
                ))
                continue

            tc = self._test_configs.get(tc_id)
            value = self.data.get(key)
            value_text = self.data.get(f'value_text_{tc_id}_{f_id}', '')

            # 数据类型校验
            if tc and tc.data_type == 'NUMBER' and value:
                try:
                    from decimal import Decimal, InvalidOperation
                    Decimal(value)
                except (InvalidOperation, ValueError):
                    errors.append(ValidationError(
                        f'"{tc.name}" 要求输入数值，当前值为 "{value}"'
                    ))

            if tc and tc.data_type == 'SELECT' and value_text:
                valid_options = tc.get_options_list()
                if valid_options and value_text not in valid_options:
                    errors.append(ValidationError(
                        f'"{tc.name}" 的值 "{value_text}" 不在可选项 {valid_options} 中'
                    ))

            if tc and tc.data_type == 'TEXT' and value_text:
                if len(value_text) > 50:
                    errors.append(ValidationError(
                        f'"{tc.name}" 的文本结果超过50字符限制'
                    ))

            if value or value_text:
                results.append({
                    'test_config_id': tc_id,
                    'formula_id': f_id,
                    'value': value or None,
                    'value_text': value_text,
                    'test_date': self.data.get(f'test_date_{tc_id}') or None,
                    'remark': self.data.get(f'remark_{tc_id}', ''),
                })

        if errors:
            raise ValidationError(errors)

        # 将解析结果存到 cleaned_data 供视图使用
        cleaned['results_matrix'] = results
        return cleaned
