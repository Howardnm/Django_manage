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

    def _parse_cell_key(self, key):
        """解析 POST 字段名，提取 (tc_id, f_id, field_type)。

        支持两种格式：
          value_{tc}_{f}       → NUMBER 类型
          value_text_{tc}_{f}  → TEXT/SELECT 类型

        Returns (tc_id, f_id, 'number'|'text') 或 (None, None, None)。
        """
        if key.startswith('value_text_'):
            suffix = key[len('value_text_'):]
            field_type = 'text'
        elif key.startswith('value_'):
            suffix = key[len('value_'):]
            field_type = 'number'
        else:
            return None, None, None

        # suffix 格式: "{tc_id}_{f_id}"
        try:
            sep = suffix.rfind('_')
            if sep < 0:
                return None, None, None
            tc_id = int(suffix[:sep])
            f_id = int(suffix[sep + 1:])
        except (ValueError, TypeError):
            return None, None, None

        return tc_id, f_id, field_type

    def clean(self):
        cleaned = super().clean()
        if not self.testing_task:
            raise ValidationError('缺少关联测试任务')

        # 按 (tc_id, f_id) 聚合单元格数据
        cells = {}
        errors = []

        for key in self.data:
            tc_id, f_id, field_type = self._parse_cell_key(key)
            if tc_id is None:
                continue

            if tc_id not in self._valid_test_item_ids:
                errors.append(ValidationError(
                    f'测试项目 ID={tc_id} 不属于当前测试任务'))
                continue
            if f_id not in self._valid_formula_ids:
                errors.append(ValidationError(
                    f'配方 ID={f_id} 不属于当前工单的实验单号'))
                continue

            cell_key = (tc_id, f_id)
            if cell_key not in cells:
                cells[cell_key] = {'value': None, 'value_text': ''}
            if field_type == 'number':
                cells[cell_key]['value'] = self.data.get(key) or None
            else:
                cells[cell_key]['value_text'] = self.data.get(key, '')

        # 数据校验 + 构建结果列表
        results = []
        from decimal import Decimal, InvalidOperation
        for (tc_id, f_id), cell in cells.items():
            tc = self._test_configs.get(tc_id)
            value = cell['value']
            value_text = cell['value_text']

            if not value and not value_text:
                continue

            if tc:
                if tc.data_type == 'NUMBER' and value:
                    try:
                        Decimal(value)
                    except (InvalidOperation, ValueError):
                        errors.append(ValidationError(
                            f'"{tc.name}" 要求输入数值，当前值为 "{value}"'))
                elif tc.data_type == 'SELECT' and value_text:
                    valid_options = tc.get_options_list()
                    if valid_options and value_text not in valid_options:
                        errors.append(ValidationError(
                            f'"{tc.name}" 的值 "{value_text}" 不在可选项 {valid_options} 中'))
                elif tc.data_type == 'TEXT' and value_text:
                    if len(value_text) > 50:
                        errors.append(ValidationError(
                            f'"{tc.name}" 的文本结果超过50字符限制'))

            results.append({
                'test_config_id': tc_id,
                'formula_id': f_id,
                'value': value,
                'value_text': value_text,
                'test_date': self.data.get(f'test_date_{tc_id}') or None,
                'remark': self.data.get(f'remark_{tc_id}', ''),
            })

        if errors:
            raise ValidationError(errors)

        cleaned['results_matrix'] = results
        return cleaned
