"""价格内核单测 —— 不依赖数据库，任何环境都能跑。

守护的是 app_raw_material/services/price_service.py 里两条被全项目共用的语义：
「最新单价 = 最新日期的跨工厂均价」与「近N月均价 = 日均值的均值」。
后者最容易被后人「顺手优化」成记录级均值，故有专门的判别性用例。
"""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from app_raw_material.services.price_service import (
    RawMaterialPriceLookup,
    avg_from_series,
    latest_from_series,
)

D = date


class LatestFromSeriesTests(SimpleTestCase):

    def test_empty_series_returns_none(self):
        self.assertIsNone(latest_from_series([]))

    def test_takes_last_day_of_sorted_series(self):
        series = [(D(2026, 1, 1), Decimal('10')), (D(2026, 3, 1), Decimal('12'))]
        self.assertEqual(latest_from_series(series), Decimal('12.00'))

    def test_quantizes_to_two_places(self):
        self.assertEqual(
            latest_from_series([(D(2026, 1, 1), Decimal('10.006'))]),
            Decimal('10.01'),
        )

    def test_accepts_float_and_str_values(self):
        self.assertEqual(latest_from_series([(D(2026, 1, 1), 9.5)]), Decimal('9.50'))
        self.assertEqual(latest_from_series([(D(2026, 1, 1), '9.5')]), Decimal('9.50'))

    def test_zero_price_is_a_value_not_absent(self):
        # 内核契约：None 才表示无数据，Decimal('0.00') 是有效价格
        self.assertEqual(latest_from_series([(D(2026, 1, 1), Decimal('0'))]), Decimal('0.00'))


class AvgFromSeriesTests(SimpleTestCase):
    """判别性用例：近N月均价是「日均值的均值」，不是「记录级均值」。"""

    def test_mean_of_daily_means_not_record_level_mean(self):
        # 同日两条报价 (10, 20) → 日均 15；另一日一条 30 → 日均 30
        # 日均的均值的 = (15 + 30) / 2 = 22.50
        # 记录级均值会是 (10 + 20 + 30) / 3 = 20.00
        series = [(D(2026, 1, 1), Decimal('15')), (D(2026, 1, 2), Decimal('30'))]
        self.assertEqual(avg_from_series(series, D(2026, 1, 1)), Decimal('22.50'))

    def test_cutoff_filters_out_older_days(self):
        series = [(D(2026, 1, 1), Decimal('10')), (D(2026, 3, 1), Decimal('30'))]
        self.assertEqual(avg_from_series(series, D(2026, 2, 1)), Decimal('30.00'))

    def test_cutoff_is_inclusive(self):
        series = [(D(2026, 1, 1), Decimal('10')), (D(2026, 3, 1), Decimal('30'))]
        self.assertEqual(avg_from_series(series, D(2026, 1, 1)), Decimal('20.00'))

    def test_empty_window_returns_none(self):
        series = [(D(2026, 1, 1), Decimal('10'))]
        self.assertIsNone(avg_from_series(series, D(2026, 6, 1)))

    def test_empty_series_returns_none(self):
        self.assertIsNone(avg_from_series([], D(2026, 1, 1)))

    def test_quantizes_to_two_places(self):
        series = [(D(2026, 1, 1), Decimal('10')), (D(2026, 1, 2), Decimal('10.03'))]
        # 均值 10.015 → 10.02（quantize 默认 ROUND_HALF_EVEN，进位到偶数）
        self.assertEqual(avg_from_series(series, D(2026, 1, 1)), Decimal('10.02'))


class LookupGroupingTests(SimpleTestCase):
    """查表的分组逻辑：全局维度对同日各工厂取均值，工厂维度各自成列。"""

    def _lookup(self, rows, months=6):
        # 直接注入 rows，避免测试触库
        lookup = RawMaterialPriceLookup(months=months)
        lookup._rows = rows
        return lookup

    def test_global_series_averages_across_plants_on_same_day(self):
        rows = [
            (1, 10, D(2026, 1, 1), Decimal('10')),
            (1, 20, D(2026, 1, 1), Decimal('20')),
        ]
        series = self._lookup(rows).series()
        self.assertEqual(series[1], [(D(2026, 1, 1), Decimal('15'))])

    def test_plant_series_keeps_plants_separate(self):
        rows = [
            (1, 10, D(2026, 1, 1), Decimal('10')),
            (1, 20, D(2026, 1, 1), Decimal('20')),
        ]
        lookup = self._lookup(rows)
        self.assertEqual(lookup.series(10)[1], [(D(2026, 1, 1), Decimal('10'))])
        self.assertEqual(lookup.series(20)[1], [(D(2026, 1, 1), Decimal('20'))])

    def test_series_is_sorted_by_date(self):
        rows = [
            (1, 10, D(2026, 3, 1), Decimal('30')),
            (1, 10, D(2026, 1, 1), Decimal('10')),
        ]
        self.assertEqual(
            self._lookup(rows).series(10)[1],
            [(D(2026, 1, 1), Decimal('10')), (D(2026, 3, 1), Decimal('30'))],
        )

    def test_series_cached_per_dimension(self):
        lookup = self._lookup([(1, 10, D(2026, 1, 1), Decimal('10'))])
        self.assertIs(lookup.series(10), lookup.series(10))
        self.assertIs(lookup.series(), lookup.series())

    def test_no_records_means_no_price(self):
        # 价格不落库，没有价格记录就是查不到 —— 不做任何缓存列兜底
        lookup = self._lookup([])
        self.assertIsNone(lookup.latest(1))
        self.assertIsNone(lookup.avg(1))

    def test_plant_latest_does_not_fall_back_to_global(self):
        # 该工厂没有报价就是没有，不做全局兜底
        rows = [(1, 10, D(2026, 1, 1), Decimal('10'))]
        lookup = self._lookup(rows)
        self.assertEqual(lookup.latest(1, 10), Decimal('10.00'))
        self.assertIsNone(lookup.latest(1, 20))

    def test_avg_cache_is_keyed_by_plant(self):
        rows = [
            (1, 10, D(2026, 1, 1), Decimal('10')),
            (1, 20, D(2026, 1, 1), Decimal('20')),
        ]
        lookup = self._lookup(rows)
        self.assertEqual(lookup.avg(1), Decimal('15.00'))
        self.assertEqual(lookup.avg(1, 10), Decimal('10.00'))
        self.assertEqual(lookup.avg(1, 20), Decimal('20.00'))

    def test_maps_cover_all_known_materials(self):
        lookup = RawMaterialPriceLookup(months=6, ids=[1, 2])
        lookup._rows = [(1, 10, D(2026, 1, 1), Decimal('10'))]
        self.assertEqual(set(lookup.latest_map()), {1, 2})

    def test_plant_ids_collected_from_rows(self):
        rows = [
            (1, 10, D(2026, 1, 1), Decimal('10')),
            (1, 20, D(2026, 1, 1), Decimal('20')),
        ]
        self.assertEqual(self._lookup(rows).plant_ids(), {10, 20})
