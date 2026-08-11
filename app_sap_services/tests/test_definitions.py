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
        self.assertEqual(MaterialPriceQuery.function_name, "ZRFC_GET_MBEW")
        self.assertEqual(MaterialStockQuery.function_name, "ZRFC_GET_MAT_STOCK")
        self.assertEqual(VendorCheckQuery.function_name, "ZFG_CHECK_VENDOR")


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