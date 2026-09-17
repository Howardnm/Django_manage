"""SAPGateway / RfcQuery 回归测试。

覆盖核心代码 query/gateway.py 的新增 SAPGateway.call_structured，
并用 FakeConnMgr 验证既有 RfcQuery 管线（call/collect/first/get/count/exists/exclude）
不回归。全部通过假连接执行，不触真实 SAP。
"""

from datetime import date

from django.test import SimpleTestCase

from app_sap_services import SAPFilterError
from app_sap_services.query.gateway import SAPGateway
from app_sap_services.definitions.material import MaterialQuery
from app_sap_services.definitions.price import MaterialPriceQuery
from app_sap_services.definitions.vendor import VendorCheckQuery

from .helpers import FakeConnMgr


class CallStructuredTest(SimpleTestCase):
    """新增方法 call_structured —— 校验类函数的主入口。"""

    def _vendor_raw(self):
        return {
            "ES_LFA1": {"LIFNR": "00000203100", "NAME1": "测试供应商",
                        "LAND1": "CN", "ERDAT": "20250101"},
            "ES_LFM1": {"LIFNR": "00000203100", "EKORG": "1000"},
            "ES_LFB1": {"LIFNR": "00000203100", "BUKRS": "1000"},
            "ET_RETURN": [{"TYPE": "S", "MESSAGE": "OK", "NUMBER": "1"}],
        }

    def test_returns_full_dict(self):
        conn = FakeConnMgr(self._vendor_raw())
        gw = SAPGateway(conn)
        result = gw.call_structured(
            VendorCheckQuery,
            i_vendor="0000203100", i_pur_org="1000", i_comp_code="1000",
        )
        self.assertEqual(set(result.keys()),
                         {"ES_LFA1", "ES_LFM1", "ES_LFB1", "ET_RETURN"})
        self.assertEqual(result["ES_LFA1"].LIFNR, "203100")
        self.assertEqual(result["ES_LFA1"].ERDAT, date(2025, 1, 1))
        self.assertEqual(result["ET_RETURN"][0].MESSAGE, "OK")

    def test_passes_correct_params(self):
        conn = FakeConnMgr(self._vendor_raw())
        gw = SAPGateway(conn)
        gw.call_structured(
            VendorCheckQuery,
            i_vendor="0000203100", i_pur_org="1000", i_comp_code="1000",
        )
        self.assertEqual(len(conn.calls), 1)
        fn, params = conn.calls[0]
        self.assertEqual(fn, "ZFG_CHECK_VENDOR")
        self.assertEqual(params, {
            "I_VENDOR": "0000203100",
            "I_PUR_ORG": "1000",
            "I_COMP_CODE": "1000",
        })

    def test_works_with_list_based_query_too(self):
        # call_structured 对表格输出同样可用（返回 dict 而非扁平 list）
        conn = FakeConnMgr({
            "E_RTYPE": "S", "E_RTMSG": "查询成功",
            "IT_ITEM": [{"MATNR": "A01005000057", "VERPR": "1.5"}],
        })
        gw = SAPGateway(conn)
        result = gw.call_structured(MaterialPriceQuery, s_bwkey__eq="3011")
        self.assertEqual(result["IT_ITEM"][0].VERPR, 1.5)
        # 未声明为 OutputTable 的 Export 键原样透传
        self.assertEqual(result["E_RTYPE"], "S")


class NestedStructureQueryTest(SimpleTestCase):
    """端到端参数形状 —— 嵌套在 IS_QUERY 里的 range 必须原样传给 pyrfc。"""

    _RAW = {
        "E_RTYPE": "S", "E_RTMSG": "查询成功",
        "IT_ITEM": [
            {"MATNR": "A01005000057", "BWKEY": "3011", "BDATJ": "2026",
             "POPER": "009", "PEINH": "10000", "VPRSV": "V",
             "VERPR": "93751.06", "STPRS": "0.00", "PVPRS": "0.00",
             "WAERS": "CNY", "KALNR": "000100473814"},
        ],
    }

    def test_params_sent_to_sap_are_nested(self):
        conn = FakeConnMgr(self._RAW)
        gw = SAPGateway(conn)
        gw.rfc(MaterialPriceQuery).filter(s_bwkey__eq="3011").call()
        fn, params = conn.calls[0]
        self.assertEqual(fn, "ZRFC_GET_MBEWH")
        self.assertEqual(
            params,
            {"IS_QUERY": {"S_BWKEY": [
                {"SIGN": "I", "OPTION": "EQ", "LOW": "3011", "HIGH": ""}
            ]}},
        )

    def test_exclude_on_nested_range_sets_sign_e(self):
        """exclude 作用于嵌套 range —— 曾经会因假设顶层而静默失效。"""
        gw = SAPGateway(FakeConnMgr(self._RAW))
        q = gw.rfc(MaterialPriceQuery).exclude(s_bwkey__eq="3011")
        q.call()
        self.assertEqual(
            q._build_params()["IS_QUERY"]["S_BWKEY"][0]["SIGN"], "E"
        )

    def test_collect_parses_row(self):
        gw = SAPGateway(FakeConnMgr(self._RAW))
        df = gw.rfc(MaterialPriceQuery).filter(s_bwkey__eq="3011").collect()
        self.assertEqual(df.height, 1)
        self.assertEqual(df["POPER"][0], 9)
        self.assertEqual(df["PEINH"][0], 10000)
        self.assertAlmostEqual(df["VERPR"][0] / df["PEINH"][0], 9.375106)


class RfcQueryRegressionTest(SimpleTestCase):
    """既有表格查询管线 —— 确保不回归。"""

    def _zmarc_raw(self):
        return {
            "ZMARC": [
                {"MATNR": "0000A01001", "WERKS": "1010", "MAKTX": "物料A", "MTART": "ROH"},
                {"MATNR": "0000A02002", "WERKS": "1010", "MAKTX": "物料B", "MTART": "ROH"},
            ]
        }

    def test_call_returns_records(self):
        gw = SAPGateway(FakeConnMgr(self._zmarc_raw()))
        rows = gw.rfc(MaterialQuery).filter(mat_range__cp="A01*").call()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].MATNR, "A01001")
        self.assertTrue(hasattr(rows[0], "MAKTX"))

    def test_collect_returns_dataframe(self):
        import polars as pl
        gw = SAPGateway(FakeConnMgr(self._zmarc_raw()))
        df = gw.rfc(MaterialQuery).filter(mat_range__cp="A01*").collect()
        self.assertIsInstance(df, pl.DataFrame)
        self.assertEqual(df.height, 2)

    def test_first_and_last(self):
        gw = SAPGateway(FakeConnMgr(self._zmarc_raw()))
        q = gw.rfc(MaterialQuery)
        self.assertEqual(q.clone().first().MATNR, "A01001")
        self.assertEqual(q.clone().last().MATNR, "A02002")

    def test_get_and_count(self):
        gw = SAPGateway(FakeConnMgr(self._zmarc_raw()))
        q = gw.rfc(MaterialQuery)
        self.assertEqual(q.clone().count(), 2)
        self.assertTrue(q.clone().exists())

    def test_exclude_sets_sign_e(self):
        gw = SAPGateway(FakeConnMgr(self._zmarc_raw()))
        q = gw.rfc(MaterialQuery).exclude(mat_range__cp="A01*")
        q.call()
        # 通过底层 params 验证 exclude → SIGN="E"
        params = q._build_params()
        self.assertEqual(params["MAT_RANGE"][0]["SIGN"], "E")

    def test_unknown_filter_raises_sapfiltererror(self):
        gw = SAPGateway(FakeConnMgr(self._zmarc_raw()))
        with self.assertRaises(SAPFilterError):
            gw.rfc(MaterialQuery).filter(bogus__eq="x").call()