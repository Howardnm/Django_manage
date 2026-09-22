"""转换层回归测试 —— 钉住从两个同步命令里抽取出来的现有行为。

这批测试在抽取**之前**写就（characterization tests），目的是让「把
sync_material_prices / sync_material_stock 的私有方法搬到 transforms.py」
成为可验证的机械操作，而不是一次无人察觉的口径变更。这两个命令此前
对这几个函数零测试覆盖。

全部不连 SAP、不碰数据库。
"""

from __future__ import annotations

from collections import Counter
from datetime import date

import polars as pl

from django.test import SimpleTestCase

from app_sap_services.transforms import (
    ALLOWED_CURRENCY,
    apply_period_filter,
    blank,
    clean_stock,
    current_ym,
    make_price_source,
    matnr_filter_kwargs,
    month_window,
    normalize_keys,
    period_to_date,
    period_ym,
    transform_prices,
    ym_label,
)


# ----------------------------------------------------------------------
# 帧构造
# ----------------------------------------------------------------------

PRICE_SCHEMA = {
    "KALNR": pl.Utf8,
    "BDATJ": pl.Int64,
    "POPER": pl.Int64,
    "PEINH": pl.Int64,
    "VPRSV": pl.Utf8,
    "STPRS": pl.Float64,
    "PVPRS": pl.Float64,
    "WAERS": pl.Utf8,
    "SALK3": pl.Float64,
    "SALKV": pl.Float64,
    "MATNR": pl.Utf8,
    "BWKEY": pl.Utf8,
    "VERPR": pl.Float64,
}

STOCK_SCHEMA = {
    "MATNR": pl.Utf8,
    "MAKTX": pl.Utf8,
    "WERKS": pl.Utf8,
    "LGORT": pl.Utf8,
    "CHARG": pl.Utf8,
    "CLABS": pl.Float64,
    "EISBE": pl.Float64,
}


def price_row(matnr="A01005000057", bwkey="3011", bdatj=2026, poper=9,
              peinh=1, verpr=12.5, waers="CNY", kalnr="000000000001"):
    return {
        "KALNR": kalnr, "BDATJ": bdatj, "POPER": poper, "PEINH": peinh,
        "VPRSV": "V", "STPRS": 0.0, "PVPRS": 0.0, "WAERS": waers,
        "SALK3": 0.0, "SALKV": 0.0, "MATNR": matnr, "BWKEY": bwkey,
        "VERPR": verpr,
    }


def price_df(rows=None) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=PRICE_SCHEMA)
    return pl.DataFrame(rows, schema=PRICE_SCHEMA)


def stock_row(matnr="A01005000057", werks="3011", loc="0001", charg="B1",
              clabs=10.0, eisbe=1.0):
    return {
        "MATNR": matnr, "MAKTX": "", "WERKS": werks, "LGORT": loc,
        "CHARG": charg, "CLABS": clabs, "EISBE": eisbe,
    }


def stock_df(rows=None) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame(schema=STOCK_SCHEMA)
    return pl.DataFrame(rows, schema=STOCK_SCHEMA)


# ----------------------------------------------------------------------
# blank —— 零列空帧是本模块反复出现的坑
# ----------------------------------------------------------------------

class BlankTests(SimpleTestCase):

    def test_none_is_blank(self):
        self.assertTrue(blank(None))

    def test_zero_column_frame_is_blank(self):
        """RfcQuery 无结果时返回的就是零列帧，不是带 schema 的空帧。"""
        df = pl.DataFrame()
        self.assertEqual(df.columns, [])
        self.assertTrue(blank(df))

    def test_empty_with_schema_is_blank(self):
        self.assertTrue(blank(price_df()))

    def test_non_empty_is_not_blank(self):
        self.assertFalse(blank(price_df([price_row()])))


class ZeroColumnSafetyTests(SimpleTestCase):
    """零列帧若漏了守卫，会抛 ColumnNotFoundError 而不是安静返回。"""

    def test_transforms_pass_zero_column_frame_through(self):
        df = pl.DataFrame()
        warnings = Counter()
        self.assertEqual(blank(transform_prices(df, warnings)), True)
        self.assertEqual(blank(clean_stock(df, warnings)), True)
        self.assertEqual(
            blank(apply_period_filter(
                df, None, current_ym=202609, include_future=False,
                warnings=warnings)), True)
        self.assertEqual(warnings, Counter())


# ----------------------------------------------------------------------
# normalize_keys
# ----------------------------------------------------------------------

class NormalizeKeysTests(SimpleTestCase):

    def test_strips_whitespace_on_requested_columns(self):
        df = pl.DataFrame({"MATNR": [" A01 "], "WERKS": ["3011\n"]})
        out = normalize_keys(df, ["MATNR", "WERKS"])
        self.assertEqual(out["MATNR"].to_list(), ["A01"])
        self.assertEqual(out["WERKS"].to_list(), ["3011"])

    def test_null_becomes_empty_string(self):
        df = pl.DataFrame({"MATNR": [None]}, schema={"MATNR": pl.Utf8})
        self.assertEqual(normalize_keys(df, ["MATNR"])["MATNR"].to_list(), [""])

    def test_missing_columns_are_skipped(self):
        df = pl.DataFrame({"MATNR": ["A01"]})
        out = normalize_keys(df, ["MATNR", "BWKEY"])
        self.assertEqual(out.columns, ["MATNR"])

    def test_non_string_column_is_cast(self):
        df = pl.DataFrame({"MATNR": [12345]})
        out = normalize_keys(df, ["MATNR"])
        self.assertEqual(out["MATNR"].to_list(), ["12345"])

    def test_blank_frame_passthrough(self):
        self.assertTrue(blank(normalize_keys(pl.DataFrame(), ["MATNR"])))


# ----------------------------------------------------------------------
# clean_stock
# ----------------------------------------------------------------------

class CleanStockTests(SimpleTestCase):

    def test_null_quantities_become_zero(self):
        df = pl.DataFrame(
            [{"MATNR": "A", "WERKS": "3011", "LGORT": "", "CHARG": "",
              "CLABS": None, "EISBE": None}],
            schema=STOCK_SCHEMA,
        )
        out = clean_stock(df)
        self.assertEqual(out["CLABS"].to_list(), [0.0])
        self.assertEqual(out["EISBE"].to_list(), [0.0])

    def test_empty_werks_sentinel_rows_are_dropped_and_counted(self):
        df = stock_df([
            stock_row(matnr="A", werks=""),
            stock_row(matnr="A", werks="3011"),
        ])
        warnings = Counter()
        out = clean_stock(df, warnings)
        self.assertEqual(out.height, 1)
        self.assertEqual(warnings["empty_plant"], 1)

    def test_whitespace_only_werks_counts_as_sentinel(self):
        """strip 之后才是空 → 必须在归一化之后再判哨兵。"""
        df = stock_df([stock_row(matnr="A", werks="   ")])
        warnings = Counter()
        out = clean_stock(df, warnings)
        self.assertEqual(out.height, 0)
        self.assertEqual(warnings["empty_plant"], 1)

    def test_empty_matnr_dropped(self):
        df = stock_df([stock_row(matnr="", werks="3011")])
        self.assertEqual(clean_stock(df).height, 0)

    def test_negative_clabs_dropped(self):
        df = stock_df([
            stock_row(matnr="A", clabs=-1.0),
            stock_row(matnr="A", clabs=0.0),
            stock_row(matnr="A", clabs=5.0),
        ])
        out = clean_stock(df)
        self.assertEqual(sorted(out["CLABS"].to_list()), [0.0, 5.0])

    def test_quantities_are_not_rounded(self):
        """库存保留 SAP 原精度，写库与导出共用同一套清洗。"""
        df = stock_df([stock_row(clabs=1.2345)])
        self.assertAlmostEqual(clean_stock(df)["CLABS"].to_list()[0], 1.2345)


# ----------------------------------------------------------------------
# transform_prices
# ----------------------------------------------------------------------

class TransformPricesTests(SimpleTestCase):

    def test_drops_rows_with_null_period_or_price_fields(self):
        df = price_df([
            price_row(bdatj=None),
            price_row(poper=None),
            price_row(peinh=None),
            price_row(verpr=None),
            price_row(),
        ])
        self.assertEqual(transform_prices(df).height, 1)

    def test_non_cny_is_dropped_and_counted(self):
        df = price_df([
            price_row(waers="USD"),
            price_row(waers="CNY"),
        ])
        warnings = Counter()
        out = transform_prices(df, warnings)
        self.assertEqual(out.height, 1)
        self.assertEqual(warnings["currency"], 1)
        self.assertEqual(ALLOWED_CURRENCY, "CNY")

    def test_null_currency_is_treated_as_non_cny(self):
        """WAERS 为 null 时 fill_null("") 后不等于 CNY → 丢弃，不是误留。"""
        df = price_df([price_row(waers=None)])
        warnings = Counter()
        self.assertEqual(transform_prices(df, warnings).height, 0)
        self.assertEqual(warnings["currency"], 1)

    def test_peinh_filtered_before_division(self):
        """先 PEINH>0 再相除，否则会得到 inf/nan 并污染后续比较。"""
        df = price_df([price_row(peinh=0, verpr=10.0)])
        self.assertEqual(transform_prices(df).height, 0)

    def test_unit_price_is_verpr_over_peinh(self):
        df = price_df([price_row(peinh=1, verpr=12.5)])
        self.assertAlmostEqual(
            transform_prices(df)["UNIT_PRICE"].to_list()[0], 12.5)

    def test_peinh_10000_divides(self):
        """PEINH 实测取值为 1 与 10000，除法不可省。"""
        df = price_df([price_row(peinh=10000, verpr=125000.0)])
        self.assertAlmostEqual(
            transform_prices(df)["UNIT_PRICE"].to_list()[0], 12.5)

    def test_non_positive_unit_price_dropped(self):
        df = price_df([price_row(peinh=1, verpr=0.0)])
        self.assertEqual(transform_prices(df).height, 0)

    def test_negative_unit_price_dropped(self):
        df = price_df([price_row(peinh=1, verpr=-5.0)])
        self.assertEqual(transform_prices(df).height, 0)

    def test_dedupe_keeps_max_kalnr(self):
        df = price_df([
            price_row(kalnr="000000000001", verpr=10.0),
            price_row(kalnr="000000000002", verpr=20.0),
        ])
        warnings = Counter()
        out = transform_prices(df, warnings)
        self.assertEqual(out.height, 1)
        self.assertEqual(warnings["dedupe"], 1)
        self.assertAlmostEqual(out["UNIT_PRICE"].to_list()[0], 20.0)

    def test_dedupe_is_per_material_plant_period(self):
        df = price_df([
            price_row(bwkey="3011", verpr=10.0),
            price_row(bwkey="3011", verpr=20.0, kalnr="000000000002"),
            price_row(bwkey="3020", verpr=30.0),
        ])
        out = transform_prices(df)
        self.assertEqual(out.height, 2)
        self.assertEqual(sorted(out["BWKEY"].to_list()), ["3011", "3020"])

    # ── price_decimals 的两条路径 ──

    def test_write_path_rounds_to_2_and_drops_sub_half_cent(self):
        """写库路径（默认）的既有行为：先舍入再判 > 0。

        PEINH=10000、VERPR=40 时真实单价 0.004，舍入后变 0 被丢弃。
        这是**现有行为**，抽取时必须保持不变。
        """
        df = price_df([price_row(peinh=10000, verpr=40.0)])
        self.assertEqual(transform_prices(df, price_decimals=2).height, 0)

    def test_export_path_keeps_sub_half_cent_price(self):
        """导出路径传 None：保留原商判断，<0.005 的真实价格不被吞掉。

        这是两条路径**有意**的差异，不是遗漏 —— 入库时看不出来，
        导成 Excel 就是个空白格。
        """
        df = price_df([price_row(peinh=10000, verpr=40.0)])
        out = transform_prices(df, price_decimals=None)
        self.assertEqual(out.height, 1)
        self.assertAlmostEqual(out["UNIT_PRICE"].to_list()[0], 0.004)

    def test_export_path_still_drops_true_zero(self):
        df = price_df([price_row(peinh=10000, verpr=0.0)])
        self.assertEqual(
            transform_prices(df, price_decimals=None).height, 0)

    def test_blank_frame_passthrough(self):
        self.assertTrue(blank(transform_prices(price_df())))


# ----------------------------------------------------------------------
# apply_period_filter
# ----------------------------------------------------------------------

class ApplyPeriodFilterTests(SimpleTestCase):

    def test_drops_null_period_fields(self):
        df = price_df([price_row(bdatj=None), price_row()])
        out = apply_period_filter(
            df, None, current_ym=202612, include_future=True)
        self.assertEqual(out.height, 1)

    def test_future_periods_truncated_and_counted(self):
        df = price_df([
            price_row(bdatj=2026, poper=9),
            price_row(bdatj=2026, poper=10),
        ])
        warnings = Counter()
        out = apply_period_filter(
            df, None, current_ym=202609, include_future=False,
            warnings=warnings)
        self.assertEqual(out["POPER"].to_list(), [9])
        self.assertEqual(warnings["future"], 1)

    def test_include_future_keeps_them(self):
        df = price_df([
            price_row(bdatj=2026, poper=9),
            price_row(bdatj=2026, poper=10),
        ])
        out = apply_period_filter(
            df, None, current_ym=202609, include_future=True)
        self.assertEqual(sorted(out["POPER"].to_list()), [9, 10])

    def test_range_is_inclusive_on_both_ends(self):
        df = price_df([
            price_row(bdatj=2025, poper=12),
            price_row(bdatj=2026, poper=1),
            price_row(bdatj=2026, poper=2),
            price_row(bdatj=2026, poper=3),
        ])
        out = apply_period_filter(
            df, (202601, 202602), current_ym=202612, include_future=True)
        self.assertEqual(
            sorted(out["POPER"].to_list()), [1, 2])

    def test_ym_arithmetic_spans_year_boundary(self):
        """202512 < 202601 —— 整数比较成立，无需拆年。"""
        df = price_df([
            price_row(bdatj=2025, poper=12),
            price_row(bdatj=2026, poper=1),
        ])
        out = apply_period_filter(
            df, (202601, 202601), current_ym=202612, include_future=True)
        self.assertEqual(out["BDATJ"].to_list(), [2026])


# ----------------------------------------------------------------------
# 会计期间辅助
# ----------------------------------------------------------------------

class PeriodHelperTests(SimpleTestCase):

    def test_period_ym(self):
        self.assertEqual(period_ym(2026, 9), 202609)
        self.assertEqual(period_ym("2026", "09"), 202609)

    def test_period_ym_out_of_range_periods_are_arithmetic(self):
        """POPER 0/13 得到永远匹配不上窗口的 YYYY00 / YYYY13，由调用方计数。"""
        self.assertEqual(period_ym(2026, 0), 202600)
        self.assertEqual(period_ym(2026, 13), 202613)

    def test_period_ym_none(self):
        self.assertIsNone(period_ym(None, 1))
        self.assertIsNone(period_ym(2026, None))

    def test_period_to_date(self):
        self.assertEqual(period_to_date(2026, 9), date(2026, 9, 1))

    def test_period_to_date_rejects_adjustment_period(self):
        """POPER=13 是调整期间，没有对应日期。"""
        self.assertIsNone(period_to_date(2026, 13))

    def test_period_to_date_rejects_zero_period(self):
        self.assertIsNone(period_to_date(2026, 0))

    def test_period_to_date_rejects_missing(self):
        self.assertIsNone(period_to_date(None, 9))
        self.assertIsNone(period_to_date(2026, None))

    def test_make_price_source(self):
        self.assertEqual(
            make_price_source(2026, 1, "3011"), "SAP MBEWH 2026-01 [3011]")

    def test_make_price_source_without_plant(self):
        self.assertEqual(make_price_source(2026, 1), "SAP MBEWH 2026-01")

    def test_current_ym_can_be_injected(self):
        self.assertEqual(current_ym(date(2026, 9, 30)), 202609)


# ----------------------------------------------------------------------
# 月份窗口
# ----------------------------------------------------------------------

class MonthWindowTests(SimpleTestCase):

    def test_crosses_year_boundary(self):
        self.assertEqual(
            month_window(202603, 12),
            [202504, 202505, 202506, 202507, 202508, 202509,
             202510, 202511, 202512, 202601, 202602, 202603],
        )

    def test_window_of_one_is_the_end_month(self):
        self.assertEqual(month_window(202603, 1), [202603])

    def test_december_end(self):
        self.assertEqual(
            month_window(202512, 3), [202510, 202511, 202512])

    def test_ascending_and_unique(self):
        window = month_window(202601, 24)
        self.assertEqual(window, sorted(window))
        self.assertEqual(len(set(window)), 24)

    def test_rejects_non_positive_n(self):
        with self.assertRaises(ValueError):
            month_window(202601, 0)

    def test_ym_label(self):
        self.assertEqual(ym_label(202510), "2025-10")
        self.assertEqual(ym_label(202601), "2026-01")


# ----------------------------------------------------------------------
# matnr_filter_kwargs
# ----------------------------------------------------------------------

class MatnrFilterKwargsTests(SimpleTestCase):
    """从 sync_material_stock 移过来的函数，原断言见 test_sync_material_stock。"""

    def test_no_matnr_returns_empty(self):
        self.assertEqual(matnr_filter_kwargs(None), {})
        self.assertEqual(matnr_filter_kwargs(""), {})

    def test_wildcard_uses_cp(self):
        self.assertEqual(matnr_filter_kwargs("A01*"), {"mat_range__cp": "A01*"})

    def test_exact_uses_eq(self):
        self.assertEqual(
            matnr_filter_kwargs("A01005000057"),
            {"mat_range__eq": "A01005000057"})
