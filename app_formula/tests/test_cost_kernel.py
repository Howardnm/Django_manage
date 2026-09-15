"""成本内核单测 —— 不依赖数据库，任何环境都能跑。

守护两条被全项目共用的语义：
    1. 「成本 = Σ(价格 × 份数) / Σ份数」只有 weighted_unit_cost 一处实现
    2. 缺价一律返回 None（严格模式），不静默报出被稀释的假成本
"""

import calendar
from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from app_formula.services.cost_service import cost_timeline, weighted_unit_cost

D = date


class _Line:
    """FormulaBOM 替身：内核只用 percentage 与 raw_material_id。"""

    def __init__(self, percentage, rm_id=1):
        self.percentage = Decimal(str(percentage))
        self.raw_material_id = rm_id


def _prices(mapping):
    """price_of：按 rm_id 查价，缺省视为无价。"""
    return lambda line: mapping.get(line.raw_material_id)


class WeightedUnitCostTests(SimpleTestCase):

    def test_weighted_average(self):
        lines = [_Line(50, 1), _Line(50, 2)]
        self.assertEqual(
            weighted_unit_cost(lines, _prices({1: Decimal('10'), 2: Decimal('20')})),
            Decimal('15.00'),
        )

    def test_handles_parts_not_summing_to_100(self):
        # 按份数录入时总份数不等于 100，仍应归一化
        lines = [_Line(1, 1), _Line(3, 2)]
        self.assertEqual(
            weighted_unit_cost(lines, _prices({1: Decimal('10'), 2: Decimal('20')})),
            Decimal('17.50'),
        )

    def test_missing_price_on_any_line_returns_none(self):
        # 严格模式：缺价不下结论，而不是把缺价行当成 0 算出偏低的成本
        lines = [_Line(50, 1), _Line(50, 2)]
        self.assertIsNone(weighted_unit_cost(lines, _prices({1: Decimal('10')})))

    def test_zero_percentage_line_without_price_is_ignored(self):
        # 0 份的行对成本没有贡献，缺价不应拖垮结果
        lines = [_Line(0, 1), _Line(100, 2)]
        self.assertEqual(
            weighted_unit_cost(lines, _prices({2: Decimal('10')})),
            Decimal('10.00'),
        )

    def test_all_zero_percentage_returns_none(self):
        self.assertIsNone(
            weighted_unit_cost([_Line(0, 1)], _prices({1: Decimal('10')}))
        )

    def test_no_lines_returns_none(self):
        self.assertIsNone(weighted_unit_cost([], _prices({})))

    def test_zero_price_is_a_value_not_absent(self):
        # Decimal('0.00') 是有效价格；只有 None 才表示缺价
        self.assertEqual(
            weighted_unit_cost([_Line(100, 1)], _prices({1: Decimal('0')})),
            Decimal('0.00'),
        )

    def test_quantizes_to_two_places(self):
        lines = [_Line(1, 1), _Line(2, 2)]
        # (10*1 + 20*2) / 3 = 16.666... → 16.67
        self.assertEqual(
            weighted_unit_cost(lines, _prices({1: Decimal('10'), 2: Decimal('20')})),
            Decimal('16.67'),
        )


class CostTimelineTests(SimpleTestCase):

    def test_no_lines_returns_empty(self):
        self.assertEqual(cost_timeline([], lambda line: []), [])

    def test_no_price_dates_returns_empty(self):
        self.assertEqual(cost_timeline([_Line(100, 1)], lambda line: []), [])

    def test_locf_skips_dates_before_a_line_has_any_price(self):
        d1, d2 = D(2026, 1, 1), D(2026, 2, 1)
        lines = [_Line(50, 1), _Line(50, 2)]
        series = {
            1: [(d1, Decimal('10')), (d2, Decimal('12'))],
            2: [(d2, Decimal('20'))],
        }
        # d1 时原料 2 还没有报价 → 该点整体不输出；d2 时 (12*50 + 20*50)/100 = 16.00
        self.assertEqual(
            cost_timeline(lines, lambda line: series[line.raw_material_id]),
            [[calendar.timegm(d2.timetuple()) * 1000, 16.0]],
        )

    def test_locf_carries_forward_last_known_price(self):
        d1, d2 = D(2026, 1, 1), D(2026, 2, 1)
        lines = [_Line(100, 1)]
        series = {1: [(d1, Decimal('10'))]}
        self.assertEqual(
            cost_timeline(lines, lambda line: series[line.raw_material_id]),
            [[calendar.timegm(d1.timetuple()) * 1000, 10.0]],
        )

    def test_values_are_floats_for_json_boundary(self):
        d1 = D(2026, 1, 1)
        result = cost_timeline(
            [_Line(100, 1)],
            lambda line: [(d1, Decimal('10.5'))],
        )
        self.assertIsInstance(result[0][1], float)
        self.assertIsInstance(result[0][0], int)

    def test_zero_percentage_line_without_price_does_not_break_timeline(self):
        d1 = D(2026, 1, 1)
        lines = [_Line(0, 1), _Line(100, 2)]
        series = {1: [], 2: [(d1, Decimal('10'))]}
        self.assertEqual(
            cost_timeline(lines, lambda line: series[line.raw_material_id]),
            [[calendar.timegm(d1.timetuple()) * 1000, 10.0]],
        )
