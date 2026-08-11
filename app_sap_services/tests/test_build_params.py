"""build_params 回归测试。

覆盖 RfcSchema.build_params 的参数构建逻辑：
- RangeTableParam 的各种 __op 操作符 → SIGN/OPTION/LOW/HIGH
- 自定义 low_field/high_field（如 MTA_RANGE → MTART_LOW/MTART_HIGH）
- ImportParam 标量参数
- 未知参数 / 未知操作符 → 抛错
"""

from django.test import SimpleTestCase

from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.vendor import VendorCheckQuery


class BuildParamsRangeTableTest(SimpleTestCase):
    def test_eq_operator(self):
        params = MaterialQuery.build_params(mat_range__eq="A01001000101")
        self.assertEqual(params, {
            "MAT_RANGE": [{"SIGN": "I", "OPTION": "EQ", "LOW": "A01001000101", "HIGH": ""}]
        })

    def test_cp_operator(self):
        params = MaterialQuery.build_params(mat_range__cp="A01*")
        self.assertEqual(params["MAT_RANGE"][0]["OPTION"], "CP")
        self.assertEqual(params["MAT_RANGE"][0]["LOW"], "A01*")

    def test_bt_tuple(self):
        params = MaterialQuery.build_params(mat_range__bt=("0010", "0020"))
        row = params["MAT_RANGE"][0]
        self.assertEqual(row["OPTION"], "BT")
        self.assertEqual(row["LOW"], "0010")
        self.assertEqual(row["HIGH"], "0020")

    def test_multiple_filters_same_param(self):
        params = MaterialQuery.build_params(
            mat_range__eq="A01001000101", mat_range__cp="A01*"
        )
        self.assertEqual(len(params["MAT_RANGE"]), 2)
        self.assertEqual(params["MAT_RANGE"][0]["OPTION"], "EQ")
        self.assertEqual(params["MAT_RANGE"][1]["OPTION"], "CP")

    def test_custom_low_high_fields(self):
        # MTA_RANGE 使用 MTART_LOW / MTART_HIGH
        params = MaterialQuery.build_params(mta_range__eq="ROH")
        row = params["MTA_RANGE"][0]
        self.assertEqual(row["MTART_LOW"], "ROH")
        self.assertNotIn("LOW", row)
        self.assertNotIn("HIGH", row)

    def test_multiple_params(self):
        params = MaterialQuery.build_params(
            mat_range__eq="A01001000101", wek_range__eq="1010", mta_range__eq="ROH"
        )
        self.assertIn("MAT_RANGE", params)
        self.assertIn("WEK_RANGE", params)
        self.assertIn("MTA_RANGE", params)


class BuildParamsImportTest(SimpleTestCase):
    def test_price_import_params(self):
        params = MaterialPriceQuery.build_params(p_lfgja="2026", p_lfmon="07")
        self.assertEqual(params, {"P_LFGJA": "2026", "P_LFMON": "07"})

    def test_vendor_import_params(self):
        params = VendorCheckQuery.build_params(
            i_vendor="0000203100", i_pur_org="1000",
            i_comp_code="1000", i_sortl="ACC",
        )
        self.assertEqual(params, {
            "I_VENDOR": "0000203100",
            "I_PUR_ORG": "1000",
            "I_COMP_CODE": "1000",
            "I_SORTL": "ACC",
        })

    def test_vendor_partial_params(self):
        # 只传供应商号，其余缺省
        params = VendorCheckQuery.build_params(i_vendor="0000203100")
        self.assertEqual(params, {"I_VENDOR": "0000203100"})


class BuildParamsErrorTest(SimpleTestCase):
    def test_unknown_param_raises(self):
        with self.assertRaises(ValueError):
            MaterialQuery.build_params(unknown__eq="x")

    def test_unknown_plain_key_raises(self):
        with self.assertRaises(ValueError):
            VendorCheckQuery.build_params(i_bad="x")

    def test_bt_needs_tuple(self):
        with self.assertRaises(ValueError):
            MaterialQuery.build_params(mat_range__bt="not-a-tuple")

    def test_error_message_lists_available(self):
        try:
            MaterialQuery.build_params(bogus__eq="x")
            self.fail("应抛出 ValueError")
        except ValueError as e:
            self.assertIn("mat_range", str(e))