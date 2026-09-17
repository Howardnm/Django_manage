"""定义文件结构回归测试。

验证四个 RFC 定义（material/price/stock/vendor）的静态结构：
- function_name 正确
- describe() 不报错且含关键信息
- VendorCheckQuery 的输出字段子集符合预期
"""

from django.test import SimpleTestCase

from app_sap_services.definitions.vendor import VendorCheckQuery
from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.stock import MaterialStockQuery


class FunctionNameTest(SimpleTestCase):
    def test_all_function_names(self):
        self.assertEqual(MaterialQuery.function_name, "ZRFC_MATERIAL_MESN")
        self.assertEqual(MaterialPriceQuery.function_name, "ZRFC_GET_MBEWH")
        self.assertEqual(MaterialStockQuery.function_name, "ZRFC_GET_MAT_STOCK")
        self.assertEqual(VendorCheckQuery.function_name, "ZFG_CHECK_VENDOR")


class MaterialPriceQueryStructureTest(SimpleTestCase):
    """ZRFC_GET_MBEWH 定义结构回归 —— 两个 range 嵌在 IS_QUERY 结构内。"""

    def test_ranges_are_nested_in_is_query(self):
        self.assertEqual(
            MaterialPriceQuery._range_params["s_matnr"].structure, "IS_QUERY"
        )
        self.assertEqual(
            MaterialPriceQuery._range_params["s_bwkey"].structure, "IS_QUERY"
        )

    def test_structure_members(self):
        self.assertEqual(list(MaterialPriceQuery._structures.keys()), ["IS_QUERY"])
        names = {p.rfc_name for p in MaterialPriceQuery._structures["IS_QUERY"]}
        self.assertEqual(names, {"S_MATNR", "S_BWKEY"})

    def test_no_import_scalar_params(self):
        # 新接口没有任何标量 Import —— 期间筛选已下移到客户端
        self.assertEqual(MaterialPriceQuery._import_params, {})

    def test_it_item_has_all_13_fields(self):
        fields = MaterialPriceQuery.IT_ITEM._fields
        for f in ("KALNR", "BDATJ", "POPER", "PEINH", "VPRSV", "STPRS", "PVPRS",
                  "WAERS", "SALK3", "SALKV", "MATNR", "BWKEY", "VERPR"):
            self.assertIn(f, fields, f"IT_ITEM 缺少字段 {f}")
        self.assertEqual(len(fields), 13)

    def test_it_item_field_types(self):
        fields = MaterialPriceQuery.IT_ITEM._fields
        for f in ("BDATJ", "POPER", "PEINH", "KALNR"):
            self.assertEqual(
                type(fields[f]).__name__,
                "IntField" if f != "KALNR" else "CharField",
                f"{f} 类型不符",
            )
        for f in ("STPRS", "PVPRS", "SALK3", "SALKV", "VERPR"):
            self.assertEqual(type(fields[f]).__name__, "DecimalField")
        # MATNR 必须用 clean_leading_zeros 才能对齐 RawMaterial.warehouse_code
        self.assertIsNotNone(fields["MATNR"].converter)

    def test_message_fields_declared(self):
        self.assertEqual(MaterialPriceQuery.msg_type_field, "E_RTYPE")
        self.assertEqual(MaterialPriceQuery.msg_text_field, "E_RTMSG")

    def test_describe_shows_structure_path(self):
        desc = MaterialPriceQuery.describe()
        self.assertIn("IS_QUERY.S_MATNR", desc)
        self.assertIn("IS_QUERY.S_BWKEY", desc)
        self.assertIn("嵌套 Import 结构", desc)

    def test_other_queries_have_no_structures(self):
        for cls in (MaterialQuery, MaterialStockQuery, VendorCheckQuery):
            self.assertEqual(cls._structures, {}, f"{cls.__name__} 不应有嵌套结构")
            self.assertEqual(cls.msg_type_field, "", f"{cls.__name__} 不应开启消息检查")


class DescribeTest(SimpleTestCase):
    def test_describe_contains_function_name(self):
        for cls in (MaterialQuery, MaterialPriceQuery, MaterialStockQuery, VendorCheckQuery):
            desc = cls.describe()
            self.assertIn(cls.function_name, desc)

    def test_vendor_describe_lists_imports_and_structures(self):
        desc = VendorCheckQuery.describe()
        for attr in ("I_VENDOR", "I_PUR_ORG", "I_COMP_CODE", "I_SORTL"):
            self.assertIn(attr, desc)
        for t in ("ES_LFA1", "ES_LFM1", "ES_LFB1", "ET_RETURN"):
            self.assertIn(t, desc)


class VendorFieldSubsetTest(SimpleTestCase):
    """VendorCheckQuery 关键字段子集 & 类型/转换器约定。"""

    def test_es_lfa1_fields_and_converter(self):
        fields = VendorCheckQuery.ES_LFA1._fields
        for f in ("MANDT", "LIFNR", "LAND1", "NAME1", "NAME2", "NAME3", "NAME4",
                  "ORT01", "ORT02", "PSTLZ", "REGIO", "SORTL", "STRAS", "MCOD1",
                  "ANRED", "KUNNR", "KTOKK", "BRSCH", "LOEVM", "SPERR", "SPERM",
                  "SPERZ", "SPRAS", "STCD1", "STCD2", "STCEG", "TXJCD", "TELF1",
                  "TELF2", "TELFX", "TELBX", "ERDAT", "ERNAM", "AEDAT"):
            self.assertIn(f, fields, f"ES_LFA1 缺少字段 {f}")
        # 账号类字段应用 clean_leading_zeros
        self.assertIsNotNone(fields["LIFNR"].converter)
        self.assertIsNotNone(fields["KUNNR"].converter)
        # 日期字段类型
        self.assertEqual(type(fields["ERDAT"]).__name__, "DateField")
        self.assertEqual(type(fields["AEDAT"]).__name__, "DateField")

    def test_es_lfm1_fields(self):
        fields = VendorCheckQuery.ES_LFM1._fields
        for f in ("MANDT", "LIFNR", "EKORG", "ERDAT", "ERNAM", "SPERM", "LOEVM",
                  "LFABC", "WAERS", "VERKF", "TELF1", "MINBW", "ZTERM", "INCO1",
                  "INCO2", "WEBRE", "KALSK", "KZAUT", "EKGRP", "XERSY", "PLIFZ",
                  "MRPPP", "LFRHY", "EIKTO", "VSBED", "NRGEW"):
            self.assertIn(f, fields, f"ES_LFM1 缺少字段 {f}")
        self.assertEqual(type(fields["MINBW"]).__name__, "DecimalField")
        self.assertEqual(type(fields["PLIFZ"]).__name__, "IntField")

    def test_es_lfb1_fields(self):
        fields = VendorCheckQuery.ES_LFB1._fields
        for f in ("MANDT", "LIFNR", "BUKRS", "ERDAT", "ERNAM", "SPERR", "LOEVM",
                  "ZUAWA", "AKONT", "BEGRU", "VZSKZ", "ZWELS", "ZTERM", "EIKTO",
                  "ZSABE", "KVERM", "FDGRV", "LNRZE", "LNRZB", "XDEZV", "HBKID"):
            self.assertIn(f, fields, f"ES_LFB1 缺少字段 {f}")

    def test_et_return_fields(self):
        fields = VendorCheckQuery.ET_RETURN._fields
        for f in ("TYPE", "ID", "NUMBER", "MESSAGE", "LOG_NO", "LOG_MSG_NO",
                  "MESSAGE_V1", "MESSAGE_V2", "MESSAGE_V3", "MESSAGE_V4",
                  "PARAMETER", "ROW", "FIELD", "SYSTEM"):
            self.assertIn(f, fields, f"ET_RETURN 缺少字段 {f}")
        self.assertEqual(type(fields["NUMBER"]).__name__, "IntField")
        self.assertEqual(type(fields["ROW"]).__name__, "IntField")

    def test_vendor_import_params(self):
        self.assertEqual(VendorCheckQuery._import_params["i_vendor"].rfc_name, "I_VENDOR")
        self.assertEqual(VendorCheckQuery._import_params["i_pur_org"].rfc_name, "I_PUR_ORG")
        self.assertEqual(VendorCheckQuery._import_params["i_comp_code"].rfc_name, "I_COMP_CODE")
        self.assertEqual(VendorCheckQuery._import_params["i_sortl"].rfc_name, "I_SORTL")