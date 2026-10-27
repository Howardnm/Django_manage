"""BOM 只读查询。走真实 schema 解析，连接是假的。"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from app_sap_services.exceptions import SAPBusinessError
from app_sap_services.query.gateway import SAPGateway
from app_sap_services.selectors.bom import get_bom, list_bom_links

from .helpers import FakeConnMgr


def _gateway(raw):
    return SAPGateway(FakeConnMgr(raw))


class ListBomLinksTest(SimpleTestCase):
    def test_empty_text_is_an_empty_list(self):
        gw = _gateway({
            "E_RTYPE": "E",
            "E_RTMSG": "查询不到相关数据",
            "IT_ITEM": [],
        })
        with patch("app_sap_services.selectors.bom.sap", gw):
            rows = list_bom_links(matnr="A02006999999", werks="3011")
        self.assertEqual(rows, [])

    def test_other_error_raises(self):
        gw = _gateway({
            "E_RTYPE": "E",
            "E_RTMSG": "无权限",
            "IT_ITEM": [],
        })
        with patch("app_sap_services.selectors.bom.sap", gw):
            with self.assertRaises(SAPBusinessError):
                list_bom_links(matnr="A02006000027", werks="3011")

    def test_projects_header_without_mandt(self):
        gw = _gateway({
            "E_RTYPE": "S",
            "E_RTMSG": "查询成功",
            "IT_ITEM": [{
                "MANDT": "400",
                "MATNR": "A02006000027",
                "WERKS": "3011",
                "STLAN": "1",
                "STLNR": "00043885",
                "STLAL": "01",
                "LOSVN": Decimal("0.000"),
                "LOSBS": Decimal("0.000"),
                "ANDAT": "20251015",
                "ANNAM": "USER1",
                "AEDAT": "",
                "AENAM": "",
                "CSLTY": "",
            }],
        })
        with patch("app_sap_services.selectors.bom.sap", gw):
            rows = list_bom_links(matnr="A02006000027", werks="3011")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("mandt", row)
        self.assertNotIn("MANDT", row)
        self.assertEqual(row["matnr"], "A02006000027")
        self.assertEqual(row["stlnr"], "00043885")
        self.assertEqual(row["andat"], "2025-10-15")
        self.assertIsNone(row["aedat"])
        self.assertEqual(row["losvn"], 0.0)


class GetBomTest(SimpleTestCase):
    def _row(self, **overrides):
        raw = {
            "STLNR": "00043885",
            "STLAN": "1",
            "STLAL": "01",
            "WERKS": "3011",
            "POSNR": "0020",
            "POSTP": "L",
            "IDNRK": "A01005000044",
            "MENGE": Decimal("649.800"),
            "MEINS": "KG",
            "AUSCH": Decimal("0.00"),
            "POTX1": "",
            "EWAHR": Decimal("98"),
            "ALPGR": "A",
            "DATUV": "20250901",
        }
        raw.update(overrides)
        return raw

    def test_datuv_and_emeng_are_converted(self):
        conn = FakeConnMgr({
            "E_RTYPE": "",
            "E_RTMSG": "",
            "GT_STB": [self._row()],
        })
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="01",
                datuv=date(2026, 10, 15),
                emeng=Decimal("1.5"),
            )
        self.assertEqual(len(conn.calls), 1)
        function, params = conn.calls[0]
        self.assertEqual(function, "ZRFC_GET_MATERIAL_BOM")
        self.assertEqual(params["I_DATUV"], "20261015")
        self.assertEqual(params["I_EMENG"], Decimal("1.5"))
        self.assertIsInstance(params["I_EMENG"], Decimal)
        self.assertNotIn("I_STLAN", params)
        self.assertEqual(result["datuv"], "2026-10-15")
        self.assertEqual(result["emeng"], "1.5")
        self.assertEqual(result["stlnr"], "00043885")
        item = result["items"][0]
        self.assertEqual(set(item), {
            "stlnr", "stlan", "stlal", "werks", "posnr", "postp", "idnrk",
            "menge", "meins", "ausch", "potx1", "ewahr", "alpgr", "datuv",
        })
        self.assertEqual(item["menge"], 649.8)
        self.assertEqual(item["ewahr"], 98)
        self.assertEqual(item["datuv"], "2025-09-01")

    def test_emeng_omitted_is_not_sent(self):
        conn = FakeConnMgr({
            "E_RTYPE": "",
            "E_RTMSG": "",
            "GT_STB": [self._row()],
        })
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="01",
                datuv=date(2026, 10, 15),
            )
        self.assertNotIn("I_EMENG", conn.calls[0][1])
        self.assertIsNone(result["emeng"])

    def test_wrong_alternative_is_missing(self):
        conn = FakeConnMgr({
            "E_RTYPE": "",
            "E_RTMSG": "",
            "GT_STB": [self._row(STLAL="01")],
        })
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="02",
                datuv=date(2026, 10, 15),
            )
        self.assertIsNone(result)
        self.assertEqual(len(conn.calls), 2)
        self.assertEqual(conn.closed, 1)

    def test_stale_connection_is_dropped_and_reread(self):
        conn = FakeConnMgr(responses=[
            {
                "E_RTYPE": "",
                "E_RTMSG": "",
                "GT_STB": [self._row(STLAL="01")],
            },
            {
                "E_RTYPE": "",
                "E_RTMSG": "",
                "GT_STB": [self._row(STLAL="02", IDNRK="A01002000009")],
            },
        ])
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="02",
                datuv=date(2026, 10, 15),
            )
        self.assertEqual(result["items"][0]["idnrk"], "A01002000009")
        self.assertEqual(result["stlal"], "02")
        self.assertEqual(len(conn.calls), 2)
        self.assertEqual(conn.closed, 1)

    def test_matching_read_keeps_the_connection(self):
        conn = FakeConnMgr({
            "E_RTYPE": "",
            "E_RTMSG": "",
            "GT_STB": [self._row()],
        })
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="01",
                datuv=date(2026, 10, 15),
            )
        self.assertIsNotNone(result)
        self.assertEqual(len(conn.calls), 1)
        self.assertEqual(conn.closed, 0)

    def test_wrong_usage_is_missing(self):
        conn = FakeConnMgr({
            "E_RTYPE": "",
            "E_RTMSG": "",
            "GT_STB": [self._row(STLAN="1", STLAL="01")],
        })
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="2",
                stlal="01",
                datuv=date(2026, 10, 15),
            )
        self.assertIsNone(result)

    def test_same_item_number_keeps_every_row(self):
        conn = FakeConnMgr({
            "E_RTYPE": "",
            "E_RTMSG": "",
            "GT_STB": [
                self._row(IDNRK="A01005000044", EWAHR=Decimal("98")),
                self._row(IDNRK="A01005000045", EWAHR=Decimal("1")),
            ],
        })
        with patch("app_sap_services.selectors.bom.sap", SAPGateway(conn)):
            result = get_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="01",
                datuv=date(2026, 10, 15),
            )
        self.assertEqual(
            [item["idnrk"] for item in result["items"]],
            ["A01005000044", "A01005000045"],
        )
        self.assertEqual(result["items"][0]["posnr"], result["items"][1]["posnr"])
