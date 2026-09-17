"""build_params 回归测试。

覆盖 RfcSchema.build_params 的参数构建逻辑：
- RangeTableParam 的各种 __op 操作符 → SIGN/OPTION/LOW/HIGH
- 自定义 low_field/high_field（如 MTA_RANGE → MTART_LOW/MTART_HIGH）
- ImportParam 标量参数
- structure= 嵌套在 Import 结构内的 range（如 ZRFC_GET_MBEWH 的 IS_QUERY）
- 未知参数 / 未知操作符 → 抛错
"""

from django.test import SimpleTestCase

from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.vendor import VendorCheckQuery
from app_sap_services.schemas import (
    RfcSchema, RangeTableParam, ImportParam, TableInput, OutputTable, CharField,
)


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


class _NestedDemo(RfcSchema):
    """测试专用：覆盖「结构内 range + 结构内标量 + 顶层 range + TableInput」四种形态。"""

    function_name = "ZRFC_NESTED_DEMO"

    top_range = RangeTableParam("TOP_RANGE", field="MATNR")
    inner_range = RangeTableParam("INNER_RANGE", field="MATNR", structure="IS_QUERY")
    inner_range2 = RangeTableParam("INNER_RANGE2", field="WERKS", structure="IS_QUERY")
    inner_scalar = ImportParam("IV_MODE", structure="IS_QUERY")
    outer_scalar = ImportParam("IV_FLAG")
    items = TableInput("IT_ITEMS")

    class IT_OUT(OutputTable):
        MATNR = CharField("物料编号")


class BuildParamsNestedStructureTest(SimpleTestCase):
    """structure= 参数应写入嵌套 dict 而非平铺到顶层。"""

    def test_nested_range_goes_into_structure(self):
        params = MaterialPriceQuery.build_params(s_bwkey__eq="3011")
        self.assertEqual(params, {
            "IS_QUERY": {
                "S_BWKEY": [{"SIGN": "I", "OPTION": "EQ", "LOW": "3011", "HIGH": ""}]
            }
        })

    def test_two_ranges_share_one_structure(self):
        params = MaterialPriceQuery.build_params(
            s_bwkey__eq="3011", s_matnr__cp="A01*"
        )
        self.assertEqual(list(params.keys()), ["IS_QUERY"])
        inner = params["IS_QUERY"]
        self.assertEqual(inner["S_BWKEY"][0]["LOW"], "3011")
        self.assertEqual(inner["S_MATNR"][0]["OPTION"], "CP")
        self.assertEqual(inner["S_MATNR"][0]["LOW"], "A01*")

    def test_nested_range_multiple_rows_same_table(self):
        params = MaterialPriceQuery.build_params(
            s_matnr__eq="A01", s_matnr__cp="A02*"
        )
        self.assertEqual(len(params["IS_QUERY"]["S_MATNR"]), 2)

    def test_nested_bt_tuple(self):
        params = MaterialPriceQuery.build_params(s_bwkey__bt=("3011", "3021"))
        row = params["IS_QUERY"]["S_BWKEY"][0]
        self.assertEqual(row["OPTION"], "BT")
        self.assertEqual(row["LOW"], "3011")
        self.assertEqual(row["HIGH"], "3021")

    def test_no_filters_yields_empty_params(self):
        # 所有入参在 SAP 侧都是 optional=True，空参数是合法调用
        self.assertEqual(MaterialPriceQuery.build_params(), {})

    def test_structure_groups_members(self):
        self.assertEqual(
            sorted(MaterialPriceQuery._structures.keys()), ["IS_QUERY"]
        )
        names = {p.rfc_name for p in MaterialPriceQuery._structures["IS_QUERY"]}
        self.assertEqual(names, {"S_MATNR", "S_BWKEY"})

    def test_nested_scalar_and_top_level_mixed(self):
        params = _NestedDemo.build_params(
            top_range__eq="A01",
            inner_range__eq="B02",
            inner_range2__eq="3011",
            inner_scalar="X",
            outer_scalar="Y",
            items=[{"MATNR": "A01"}],
        )
        self.assertEqual(params["TOP_RANGE"][0]["LOW"], "A01")
        self.assertEqual(params["IV_FLAG"], "Y")
        self.assertEqual(params["IT_ITEMS"], [{"MATNR": "A01"}])
        self.assertEqual(params["IS_QUERY"]["INNER_RANGE"][0]["LOW"], "B02")
        self.assertEqual(params["IS_QUERY"]["INNER_RANGE2"][0]["LOW"], "3011")
        self.assertEqual(params["IS_QUERY"]["IV_MODE"], "X")

    def test_range_rows_helper_handles_both_layouts(self):
        """_range_rows 必须同时兼容顶层与嵌套，否则 exclude 会静默失效。"""
        nested = MaterialPriceQuery.build_params(s_bwkey__eq="3011")
        rp_nested = MaterialPriceQuery._range_params["s_bwkey"]
        self.assertEqual(len(MaterialPriceQuery._range_rows(nested, rp_nested)), 1)

        flat = _NestedDemo.build_params(top_range__eq="A01")
        rp_flat = _NestedDemo._range_params["top_range"]
        self.assertEqual(len(_NestedDemo._range_rows(flat, rp_flat)), 1)

        # 不存在时返回空列表而非抛错
        self.assertEqual(_NestedDemo._range_rows({}, rp_flat), [])


class BuildParamsStructureValidationTest(SimpleTestCase):
    def test_structure_name_colliding_with_top_level_raises(self):
        with self.assertRaises(TypeError) as ctx:
            class _Bad(RfcSchema):
                function_name = "ZRFC_BAD"
                top = RangeTableParam("IS_QUERY", field="MATNR")
                inner = RangeTableParam("S_MATNR", field="MATNR", structure="IS_QUERY")
        self.assertIn("重名", str(ctx.exception))


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