"""BOM 写入。不先读，不连 SAP。"""

from unittest.mock import patch

from django.test import SimpleTestCase

from app_sap_services.exceptions import SAPBusinessError
from app_sap_services.query.gateway import SAPGateway
from app_sap_services.services.bom import (
    BomMaintainError,
    create_bom,
    delete_bom,
    update_bom,
)

from .helpers import FakeConnMgr


_LINE = {
    "MATNR": "NOPE",
    "WERKS": "9999",
    "STLAN": "9",
    "STLAL": "99",
    "POSNR": "0010",
    "POSTP": "L",
    "IDNRK": "A01005000044",
    "MENGE": "649.800",
    "MEINS": "KG",
    "DATUV": "2026-10-16",
}


def _ok_msg():
    return {
        "TYPE": "S",
        "ID": "M3",
        "NUMBER": "0",
        "MESSAGE": "成功",
        "ROW": "0",
        "FIELD": "",
    }


class MaintainBomTest(SimpleTestCase):
    def test_create_sends_one_write_and_keeps_strings(self):
        conn = FakeConnMgr({"T_MSG": [_ok_msg()]})
        with patch("app_sap_services.services.bom.sap", SAPGateway(conn)):
            messages = create_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="01",
                lines=[_LINE],
            )
        self.assertEqual(len(conn.calls), 1)
        function, params = conn.calls[0]
        self.assertEqual(function, "ZRFC_BOM_CREATE_FOR_PLM")
        self.assertEqual(params["I_TYPE"], "N")
        row = params["T_MAIN"][0]
        self.assertEqual(row["MATNR"], "A02006000027")
        self.assertEqual(row["WERKS"], "3011")
        self.assertEqual(row["STLAN"], "1")
        self.assertEqual(row["STLAL"], "01")
        self.assertEqual(row["MENGE"], "649.800")
        self.assertEqual(row["MEINS"], "KG")
        self.assertEqual(row["DATUV"], "2026-10-16")
        self.assertIsInstance(row["MENGE"], str)
        self.assertNotIn("BMENG", row)
        self.assertNotIn("POTX1", row)
        self.assertNotIn("EWAHR", row)
        self.assertNotIn("STKTX", row)
        self.assertNotIn("ZTEXT", row)
        self.assertEqual(messages[0]["type"], "S")
        self.assertEqual(messages[0]["text"], "成功")
        self.assertEqual(conn.closed, 1)

    def test_update_does_not_read_first(self):
        conn = FakeConnMgr({"T_MSG": [_ok_msg(), {
            "TYPE": "W", "ID": "", "NUMBER": "2", "MESSAGE": "注意", "ROW": "0", "FIELD": "",
        }]})
        with patch("app_sap_services.services.bom.sap", SAPGateway(conn)):
            messages = update_bom(
                matnr="A02006000027",
                werks="3011",
                stlan="1",
                stlal="01",
                lines=[_LINE],
            )
        self.assertEqual([call[0] for call in conn.calls], ["ZRFC_BOM_CREATE_FOR_PLM"])
        self.assertEqual(conn.calls[0][1]["I_TYPE"], "M")
        self.assertEqual([m["type"] for m in messages], ["S", "W"])

    def test_error_message_raises_with_every_row(self):
        conn = FakeConnMgr({"T_MSG": [
            {"TYPE": "E", "ID": "M3", "NUMBER": "1", "MESSAGE": "组件不存在",
             "ROW": "1", "FIELD": "IDNRK"},
            {"TYPE": "W", "ID": "", "NUMBER": "2", "MESSAGE": "注意", "ROW": "0", "FIELD": ""},
        ]})
        with patch("app_sap_services.services.bom.sap", SAPGateway(conn)):
            with self.assertRaises(BomMaintainError) as caught:
                create_bom(
                    matnr="A02006000027",
                    werks="3011",
                    stlan="1",
                    stlal="01",
                    lines=[_LINE],
                )
        self.assertEqual([m["type"] for m in caught.exception.messages], ["E", "W"])
        self.assertEqual(caught.exception.messages[0]["text"], "组件不存在")
        self.assertEqual(len(conn.calls), 1)


class DeleteBomTest(SimpleTestCase):
    def test_delete_uses_call_structured(self):
        conn = FakeConnMgr({"E_RTYPE": "S", "E_RTMSG": "删除成功"})
        with patch("app_sap_services.services.bom.sap", SAPGateway(conn)):
            result = delete_bom(
                matnr="A02006000027", werks="3011", stlan="1", stlal="01",
            )
        self.assertEqual(len(conn.calls), 1)
        function, params = conn.calls[0]
        self.assertEqual(function, "ZRFC_DELETE_MATERIAL_BOM")
        self.assertEqual(params, {
            "I_MATNR": "A02006000027",
            "I_WERKS": "3011",
            "I_STLAN": "1",
            "I_STALT": "01",
        })
        self.assertEqual(result, {"rtype": "S", "rtmsg": "删除成功"})

    def test_delete_error_raises(self):
        conn = FakeConnMgr({"E_RTYPE": "E", "E_RTMSG": "BOM 不存在"})
        with patch("app_sap_services.services.bom.sap", SAPGateway(conn)):
            with self.assertRaises(SAPBusinessError):
                delete_bom(matnr="A02006000027", werks="3011", stlan="1", stlal="01")
