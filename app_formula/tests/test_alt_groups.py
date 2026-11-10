"""替代组：一组只算一次。不连数据库。"""

from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from app_formula.services.alt_groups import (
    AltGroupError,
    dose_shares,
    validate_alt_rows,
)
from app_formula.services.cost_service import weighted_unit_cost


def _line(**kwargs):
    data = {
        'alt_group': '',
        'alt_strategy': '',
        'alt_priority': None,
        'usage_percent': None,
        'percentage': Decimal('60'),
        'raw_material_id': 1,
        'feeding_port': '1_MAIN',
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def _prices(mapping):
    return lambda line: mapping.get(line.raw_material_id)


class AltGroupValidationTests(SimpleTestCase):

    def test_strategy_one_requires_usage_to_sum_to_100(self):
        rows = [
            {'raw_material': 1, 'percentage': '60', 'alt_group': 'a', 'alt_strategy': '1',
             'alt_priority': None, 'usage_percent': '70'},
            {'raw_material': 2, 'percentage': '60', 'alt_group': 'A', 'alt_strategy': '1',
             'alt_priority': None, 'usage_percent': '30'},
        ]
        validate_alt_rows(rows)

    def test_strategy_two_priorities_must_be_contiguous(self):
        rows = [
            {'raw_material': 1, 'percentage': '60', 'alt_group': 'A', 'alt_strategy': '2',
             'alt_priority': 1, 'usage_percent': None},
            {'raw_material': 2, 'percentage': '60', 'alt_group': 'A', 'alt_strategy': '2',
             'alt_priority': 3, 'usage_percent': None},
        ]
        with self.assertRaises(AltGroupError):
            validate_alt_rows(rows)

    def test_ungrouped_row_cannot_carry_the_other_columns(self):
        with self.assertRaises(AltGroupError):
            validate_alt_rows([{
                'raw_material': 1, 'percentage': '40', 'alt_group': '',
                'alt_strategy': '2', 'alt_priority': 1, 'usage_percent': None,
            }])


class AltGroupCostTests(SimpleTestCase):

    def test_strategy_two_uses_priority_one_price_once(self):
        lines = [
            _line(raw_material_id=1, alt_group='A', alt_strategy='2', alt_priority=1),
            _line(raw_material_id=2, alt_group='A', alt_strategy='2', alt_priority=2, percentage=Decimal('60')),
            _line(raw_material_id=3, percentage=Decimal('40')),
        ]
        cost = weighted_unit_cost(lines, _prices({
            1: Decimal('10'), 2: Decimal('30'), 3: Decimal('20'),
        }))
        self.assertEqual(cost, Decimal('14.00'))

    def test_strategy_one_weights_the_unit_price_by_usage(self):
        lines = [
            _line(raw_material_id=1, alt_group='A', alt_strategy='1', usage_percent=Decimal('70')),
            _line(raw_material_id=2, alt_group='A', alt_strategy='1', usage_percent=Decimal('30')),
            _line(raw_material_id=3, percentage=Decimal('40')),
        ]
        cost = weighted_unit_cost(lines, _prices({
            1: Decimal('10'), 2: Decimal('30'), 3: Decimal('20'),
        }))
        self.assertEqual(cost, Decimal('17.60'))

    def test_missing_member_price_returns_none(self):
        lines = [
            _line(raw_material_id=1, alt_group='A', alt_strategy='1', usage_percent=Decimal('70')),
            _line(raw_material_id=2, alt_group='A', alt_strategy='1', usage_percent=Decimal('30')),
        ]
        self.assertIsNone(weighted_unit_cost(lines, _prices({1: Decimal('10')})))


class AltGroupDoseTests(SimpleTestCase):

    def test_strategy_two_issues_only_priority_one(self):
        primary = _line(raw_material_id=1, alt_group='A', alt_strategy='2', alt_priority=1)
        substitute = _line(raw_material_id=2, alt_group='A', alt_strategy='2', alt_priority=2)
        doses = dose_shares([primary, substitute, _line(raw_material_id=3, percentage=Decimal('40'))])
        self.assertEqual([(line.raw_material_id, share) for line, share in doses], [
            (1, Decimal('60')),
            (3, Decimal('40')),
        ])

    def test_strategy_one_splits_one_portion(self):
        doses = dose_shares([
            _line(raw_material_id=1, alt_group='A', alt_strategy='1', usage_percent=Decimal('70')),
            _line(raw_material_id=2, alt_group='A', alt_strategy='1', usage_percent=Decimal('30')),
        ])
        shares = [share for _line, share in doses]
        self.assertEqual(shares, [Decimal('42'), Decimal('18')])
        self.assertEqual(sum(shares, Decimal('0')), Decimal('60'))
