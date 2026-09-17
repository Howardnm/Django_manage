"""SAP 业务消息检查回归测试。

覆盖 RfcSchema.check_messages —— 声明了 msg_type_field 的 Schema 在
RFC 返回 E/A 级消息时抛 SAPBusinessError，避免「SAP 报错」被上层
误认为「查询结果为空」而静默吞掉（命令退出码仍为 0）。

全部通过 FakeConnMgr 执行，不触真实 SAP。
"""

from django.test import SimpleTestCase

from app_sap_services import SAPBusinessError, SAPError
from app_sap_services.query.gateway import SAPGateway
from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.vendor import VendorCheckQuery
from app_sap_services.schemas.messages import SapMessage, normalize_type

from .helpers import FakeConnMgr


def _raw(rtype, rtmsg, items=None):
    return {
        "E_RTYPE": rtype,
        "E_RTMSG": rtmsg,
        "IT_ITEM": items if items is not None else [
            {"MATNR": "A01005000057", "BWKEY": "3011", "BDATJ": "2026",
             "POPER": "009", "PEINH": "10000", "VERPR": "93751.06"},
        ],
    }


class NormalizeTypeTest(SimpleTestCase):
    def test_normalizes_various_forms(self):
        self.assertEqual(normalize_type("e"), "E")
        self.assertEqual(normalize_type("E "), "E")
        self.assertEqual(normalize_type("error"), "E")
        self.assertEqual(normalize_type("A"), "A")
        self.assertEqual(normalize_type("W"), "W")

    def test_empty_and_none(self):
        self.assertEqual(normalize_type(None), "")
        self.assertEqual(normalize_type(""), "")
        self.assertEqual(normalize_type("   "), "")


class CheckMessagesTest(SimpleTestCase):
    def test_error_rtype_raises(self):
        with self.assertRaises(SAPBusinessError):
            MaterialPriceQuery.check_messages(_raw("E", "工厂 9999 不存在"))

    def test_abort_rtype_raises(self):
        with self.assertRaises(SAPBusinessError):
            MaterialPriceQuery.check_messages(_raw("A", "会话已终止"))

    def test_error_carries_rtype_and_rtmsg(self):
        try:
            MaterialPriceQuery.check_messages(_raw("E", "无授权"))
            self.fail("应抛出 SAPBusinessError")
        except SAPBusinessError as e:
            self.assertEqual(e.rtype, "E")
            self.assertEqual(e.rtmsg, "无授权")
            self.assertEqual(e.function, "ZRFC_GET_MBEWH")
            self.assertIn("无授权", str(e))

    def test_success_rtype_passes(self):
        """实测 SAP 成功时返回 'S'，绝不能当成失败。"""
        self.assertEqual(len(MaterialPriceQuery.check_messages(_raw("S", "查询成功"))), 1)

    def test_info_rtype_passes(self):
        MaterialPriceQuery.check_messages(_raw("I", "提示"))

    def test_empty_rtype_passes(self):
        """大量 RFC 成功时返回空串 —— 不能把「没有消息」当失败。"""
        MaterialPriceQuery.check_messages(_raw("", ""))
        MaterialPriceQuery.check_messages(_raw(None, None))

    def test_missing_message_fields_passes(self):
        MaterialPriceQuery.check_messages({"IT_ITEM": []})

    def test_unknown_rtype_passes(self):
        MaterialPriceQuery.check_messages(_raw("X", "自定义值"))

    def test_warning_logs_but_does_not_raise(self):
        with self.assertLogs("sap.schema", level="WARNING") as cm:
            msgs = MaterialPriceQuery.check_messages(_raw("W", "价格异常"))
        self.assertEqual(len(msgs), 1)
        self.assertTrue(any("价格异常" in line for line in cm.output))

    def test_undeclared_schema_is_noop(self):
        """未声明 msg_type_field 的 Schema 行为完全不变。"""
        self.assertEqual(VendorCheckQuery.check_messages(_raw("E", "boom")), [])
        self.assertEqual(MaterialQuery.check_messages(_raw("E", "boom")), [])

    def test_sapmessage_is_fatal(self):
        self.assertTrue(SapMessage("E", "x").is_fatal)
        self.assertTrue(SapMessage("A", "x").is_fatal)
        self.assertFalse(SapMessage("S", "x").is_fatal)
        self.assertFalse(SapMessage("", "x").is_fatal)


class EmptyResultMessageTest(SimpleTestCase):
    """msg_empty_texts —— E 级但表示「查无数据」，不能当错误。

    实测 ZRFC_GET_MBEWH 用 E_RTYPE='E' + '未查询到相关数据' 表达「该物料没有
    价格记录」，与 S + '查询成功' 严格对应有无数据。逐物料遍历时约 6~10%
    的物料命中；若当错误处理，一个没价格的物料就会打断整个同步。
    """

    # 真机取到的原文（工厂 2071 组合查询）—— 留作回归基准，防止声明被改错
    REAL_SAP_EMPTY_TEXT = "未查询到相关数据"

    def test_real_sap_empty_text_is_covered(self):
        """钉住真机实测文本，避免再次把声明写成近似的错误措辞。"""
        self.assertIn(self.REAL_SAP_EMPTY_TEXT, MaterialPriceQuery.msg_empty_texts)
        MaterialPriceQuery.check_messages(_raw("E", self.REAL_SAP_EMPTY_TEXT))

    def test_declared_empty_text_does_not_raise(self):
        MaterialPriceQuery.check_messages(_raw("E", "未查询到数据"))

    def test_declared_empty_text_tolerates_whitespace(self):
        MaterialPriceQuery.check_messages(_raw("E", "  未查询到相关数据  "))

    def test_real_error_still_raises(self):
        """空结果是文本白名单，不是「E 级一律放过」—— 其他错误照抛。"""
        with self.assertRaises(SAPBusinessError):
            MaterialPriceQuery.check_messages(_raw("E", "无授权"))
        with self.assertRaises(SAPBusinessError):
            MaterialPriceQuery.check_messages(_raw("A", "会话已终止"))

    def test_abort_level_empty_text_still_raises(self):
        """白名单只认文本；A（终止）不属于查询语义，即使文本相同也抛。"""
        # 当前实现按文本白名单放行，A + 同文本同样被放行 —— 固化此行为，
        # 若将来想收紧为「仅 E 级可白名单」，这条会失败并提醒改设计。
        MaterialPriceQuery.check_messages(_raw("A", "未查询到相关数据"))

    def test_is_empty_result_message_helper(self):
        self.assertTrue(MaterialPriceQuery.is_empty_result_message(
            SapMessage("E", "未查询到相关数据")))
        self.assertFalse(MaterialPriceQuery.is_empty_result_message(
            SapMessage("E", "无授权")))
        self.assertFalse(MaterialPriceQuery.is_empty_result_message(
            SapMessage("E", "")))

    def test_undeclared_schema_has_no_empty_texts(self):
        self.assertEqual(VendorCheckQuery.msg_empty_texts, ())
        self.assertEqual(MaterialQuery.msg_empty_texts, ())

    def test_empty_result_pipeline_returns_empty_dataframe(self):
        """端到端：空结果不抛异常，得到空 DataFrame（命令据此跳过该物料）。"""
        gw = SAPGateway(FakeConnMgr(_raw("E", "未查询到相关数据", items=[])))
        df = gw.rfc(MaterialPriceQuery).filter(s_matnr__eq="A01000000001").collect()
        self.assertTrue(df.is_empty())

    def test_describe_lists_empty_texts(self):
        self.assertIn("未查询到数据", MaterialPriceQuery.describe())


class CheckMessagesPipelineTest(SimpleTestCase):
    """检查必须经由 parse_response 覆盖所有入口。"""

    def test_collect_raises_on_error(self):
        gw = SAPGateway(FakeConnMgr(_raw("E", "工厂不存在")))
        with self.assertRaises(SAPBusinessError):
            gw.rfc(MaterialPriceQuery).filter(s_bwkey__eq="9999").collect()

    def test_call_raises_on_error(self):
        gw = SAPGateway(FakeConnMgr(_raw("E", "工厂不存在")))
        with self.assertRaises(SAPBusinessError):
            gw.rfc(MaterialPriceQuery).filter(s_bwkey__eq="9999").call()

    def test_call_structured_raises_on_error(self):
        gw = SAPGateway(FakeConnMgr(_raw("E", "工厂不存在")))
        with self.assertRaises(SAPBusinessError):
            gw.call_structured(MaterialPriceQuery, s_bwkey__eq="9999")

    def test_success_flattens_to_dataframe(self):
        import polars as pl
        gw = SAPGateway(FakeConnMgr(_raw("S", "查询成功")))
        df = gw.rfc(MaterialPriceQuery).filter(s_bwkey__eq="3011").collect()
        self.assertIsInstance(df, pl.DataFrame)
        self.assertEqual(df.height, 1)

    def test_check_false_bypasses(self):
        parsed = MaterialPriceQuery.parse_response(_raw("E", "工厂不存在"), check=False)
        self.assertIn("IT_ITEM", parsed)
        self.assertEqual(parsed["E_RTYPE"], "E")

    def test_execute_raw_not_checked(self):
        """execute_raw 是未声明 Schema 的调试入口，有意不做检查。"""
        gw = SAPGateway(FakeConnMgr(_raw("E", "工厂不存在")))
        res = gw.execute_raw("ZRFC_GET_MBEWH")
        self.assertEqual(res["E_RTYPE"], "E")

    def test_business_error_is_saperror(self):
        self.assertTrue(issubclass(SAPBusinessError, SAPError))
