"""parse_response 回归测试。

覆盖对核心代码 schemas/base.py#parse_response 的改动：
新增「单 dict 命中已声明 OutputTable 时做类型化转换」分支，
同时确保既有「list 输出表」行为不回归。

- 查询类定义（MaterialQuery / MaterialPriceQuery / MaterialStockQuery）: list 表格
- 校验类定义（VendorCheckQuery）: 单结构 ES_LFA1/ES_LFM1/ES_LFB1 + 表格 ET_RETURN
"""

from datetime import date

from django.test import SimpleTestCase

from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.stock import MaterialStockQuery
from app_sap_services.definitions.vendor import VendorCheckQuery


class ParseResponseListRegressionTest(SimpleTestCase):
    """list 输出表解析 —— 既有行为，确保不回归。"""

    def test_material_query_zamrc_list(self):
        raw = {
            "ZMARC": [
                {"MATNR": "0000A01001", "WERKS": "1010", "MAKTX": "物料A",
                 "MTART": "ROH", "LVORM": ""},
                {"MATNR": "0000B02002", "WERKS": "3011", "MAKTX": "物料B",
                 "MTART": "FERT", "LVORM": "X"},
            ]
        }
        parsed = MaterialQuery.parse_response(raw)
        rows = parsed["ZMARC"]
        self.assertEqual(len(rows), 2)
        # clean_leading_zeros 生效
        self.assertEqual(rows[0].MATNR, "A01001")
        self.assertEqual(rows[1].MATNR, "B02002")
        self.assertEqual(rows[0].MAKTX, "物料A")
        self.assertEqual(rows[1].LVORM, "X")

    def test_price_query_it_item_list(self):
        raw = {
            "IT_ITEM": [
                {"MATNR": "0000A01001", "BWKEY": "1010", "VERPR": "123.45",
                 "PEINH": "1000", "LFGJA": "2026", "LFMON": "07"},
            ]
        }
        parsed = MaterialPriceQuery.parse_response(raw)
        row = parsed["IT_ITEM"][0]
        self.assertEqual(row.MATNR, "A01001")
        self.assertEqual(row.VERPR, pytest_approx(123.45))
        self.assertEqual(row.PEINH, 1000)

    def test_stock_query_it_item_decimal(self):
        raw = {
            "IT_ITEM": [
                {"MATNR": "0000A01001", "WERKS": "1010", "LGORT": "0001",
                 "CHARG": "B001", "CLABS": "12.500", "EISBE": "1.000"},
            ]
        }
        parsed = MaterialStockQuery.parse_response(raw)
        row = parsed["IT_ITEM"][0]
        self.assertEqual(row.CLABS, 12.5)
        self.assertEqual(row.EISBE, 1.0)

    def test_empty_list_returns_empty(self):
        parsed = MaterialQuery.parse_response({"ZMARC": []})
        self.assertEqual(parsed["ZMARC"], [])

    def test_missing_table_key_not_present(self):
        parsed = MaterialQuery.parse_response({"OTHER": "x"})
        self.assertNotIn("ZMARC", parsed)
        self.assertEqual(parsed["OTHER"], "x")


class ParseResponseSingleStructureTest(SimpleTestCase):
    """单结构 Export —— 本次新增行为。"""

    def _raw(self):
        return {
            "ES_LFA1": {"LIFNR": "00000203100", "NAME1": "测试供应商",
                        "LAND1": "CN", "ERDAT": "20250101"},
            "ES_LFM1": {"LIFNR": "00000203100", "EKORG": "1000",
                        "MINBW": "1234.56", "PLIFZ": "5"},
            "ES_LFB1": {"LIFNR": "00000203100", "BUKRS": "1000",
                        "AKONT": "400000", "ZTERM": "0001"},
            "ET_RETURN": [
                {"TYPE": "S", "MESSAGE": "OK", "NUMBER": "1"},
                {"TYPE": "E", "MESSAGE": "ERR", "NUMBER": "2"},
            ],
        }

    def test_single_structure_typed_record(self):
        parsed = VendorCheckQuery.parse_response(self._raw())
        lfa1 = parsed["ES_LFA1"]
        # 单结构 → 类型化 OutputRecord（非 list）
        self.assertFalse(isinstance(lfa1, list))
        self.assertEqual(lfa1.LIFNR, "203100")       # clean_leading_zeros
        self.assertEqual(lfa1.NAME1, "测试供应商")
        self.assertEqual(lfa1.ERDAT, date(2025, 1, 1))  # DateField

    def test_all_three_structures_present(self):
        parsed = VendorCheckQuery.parse_response(self._raw())
        self.assertEqual(parsed["ES_LFM1"].EKORG, "1000")
        self.assertEqual(parsed["ES_LFM1"].MINBW, pytest_approx(1234.56))
        self.assertEqual(parsed["ES_LFB1"].BUKRS, "1000")
        self.assertEqual(parsed["ES_LFB1"].AKONT, "400000")

    def test_return_table_still_list(self):
        parsed = VendorCheckQuery.parse_response(self._raw())
        msgs = parsed["ET_RETURN"]
        self.assertIsInstance(msgs, list)
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].TYPE, "S")
        self.assertEqual(msgs[0].MESSAGE, "OK")
        self.assertEqual(msgs[1].TYPE, "E")

    def test_undeclared_keys_preserved_raw(self):
        raw = self._raw()
        raw["E_RTYPE"] = "S"
        raw["E_RTMSG"] = "成功"
        parsed = VendorCheckQuery.parse_response(raw)
        self.assertEqual(parsed["E_RTYPE"], "S")
        self.assertEqual(parsed["E_RTMSG"], "成功")

    def test_single_structure_with_none_fields(self):
        parsed = VendorCheckQuery.parse_response(
            {"ES_LFA1": {"LIFNR": "00000203100", "ERDAT": "00000000"}}
        )
        lfa1 = parsed["ES_LFA1"]
        self.assertEqual(lfa1.LIFNR, "203100")
        self.assertIsNone(lfa1.NAME1)      # 未提供 → None
        self.assertIsNone(lfa1.ERDAT)      # "00000000" → None (DateField)

    def test_map_record_filters_to_declared_fields(self):
        # 未声明的字段被过滤掉
        parsed = VendorCheckQuery.parse_response(
            {"ES_LFA1": {"LIFNR": "00000203100", "UNDECLARED": "x"}}
        )
        lfa1 = parsed["ES_LFA1"]
        self.assertNotIn("UNDECLARED", lfa1._data)

    def test_empty_structures_return_none(self):
        # 校验类函数：供应商不存在时 ES_* 为空字典
        parsed = VendorCheckQuery.parse_response(
            {"ES_LFA1": {}, "ES_LFM1": {}, "ES_LFB1": {}, "ET_RETURN": []}
        )
        self.assertIsNotNone(parsed["ES_LFA1"])  # map_record({}) → 空记录对象
        n_fields = len(VendorCheckQuery.ES_LFA1._fields)
        self.assertEqual(list(parsed["ES_LFA1"]._data.values()), [None] * n_fields)
        self.assertEqual(parsed["ET_RETURN"], [])


def pytest_approx(value):
    """返回一个带容差的近似值对象（Django 测试无 pytest.approx）。"""
    class _Approx:
        def __init__(self, v): self.v = v
        def __eq__(self, o):
            try: return abs(float(o) - self.v) < 1e-6
            except (TypeError, ValueError): return False
        def __repr__(self): return f"~{self.v}"
    return _Approx(value)