"""BOM HTTP 接口。视图函数被替掉，不连 SAP，也不写库。"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from app_sap_services.api.views import BomDetailView, BomListCreateView
from app_sap_services.exceptions import SAPRfcError
from app_sap_services.services.bom import BomMaintainError


factory = APIRequestFactory()


class _User:
    is_authenticated = True
    is_active = True


def _auth(request):
    force_authenticate(request, user=_User())
    return request


_LINE = {
    "posnr": "0010",
    "postp": "L",
    "idnrk": "A01005000044",
    "menge": "649.800",
    "meins": "KG",
    "datuv": "2026-10-16",
}


class BomApiAuthTest(SimpleTestCase):
    def test_anonymous_is_forbidden(self):
        request = factory.get("/api/sap/boms/", {"matnr": "A02006000027", "werks": "3011"})
        response = BomListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "not_authenticated")


class BomListApiTest(SimpleTestCase):
    def test_missing_plant_is_400(self):
        request = _auth(factory.get("/api/sap/boms/", {"matnr": "A02006000027"}))
        response = BomListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertTrue(response.data["messages"])

    @patch("app_sap_services.api.views.list_bom_links", return_value=[])
    def test_empty_list_is_200(self, listed):
        request = _auth(factory.get(
            "/api/sap/boms/", {"matnr": "A02006999999", "werks": "3011"},
        ))
        response = BomListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"count": 0, "results": []})
        listed.assert_called_once_with(matnr="A02006999999", werks="3011")

    @patch("app_sap_services.api.views.list_bom_links")
    def test_transport_error_hides_params(self, listed):
        listed.side_effect = SAPRfcError(
            "ZFG_GET_MAST", "timeout", params={"I_MATNR": "SECRET"},
        )
        request = _auth(factory.get(
            "/api/sap/boms/", {"matnr": "A02006000027", "werks": "3011"},
        ))
        response = BomListCreateView.as_view()(request)
        body = json.dumps(response.data, ensure_ascii=False)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.data["code"], "sap_transport")
        self.assertEqual(response.data["detail"], "SAP 通信失败")
        self.assertNotIn("params:", body)
        self.assertNotIn("SECRET", body)


class BomDetailApiTest(SimpleTestCase):
    def test_missing_datuv_is_400(self):
        request = _auth(factory.get("/api/sap/boms/A02006000027/3011/1/01/"))
        response = BomDetailView.as_view()(
            request, matnr="A02006000027", werks="3011", stlan="1", stlal="01",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")
        self.assertIn("datuv", response.data["messages"][0]["text"])

    @patch("app_sap_services.api.views.get_bom", return_value=None)
    def test_missing_bom_is_404(self, get_bom):
        request = _auth(factory.get(
            "/api/sap/boms/A02006000027/3011/1/02/", {"datuv": "2026-10-15"},
        ))
        response = BomDetailView.as_view()(
            request, matnr="A02006000027", werks="3011", stlan="1", stlal="02",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "not_found")
        self.assertNotIn("01", json.dumps(response.data))
        get_bom.assert_called_once()

    @patch("app_sap_services.api.views.get_bom")
    def test_detail_returns_items(self, get_bom):
        get_bom.return_value = {
            "matnr": "A02006000027",
            "werks": "3011",
            "stlan": "1",
            "stlal": "01",
            "datuv": "2026-10-15",
            "emeng": None,
            "stlnr": "00043885",
            "items": [],
        }
        request = _auth(factory.get(
            "/api/sap/boms/A02006000027/3011/1/01/", {"datuv": "2026-10-15"},
        ))
        response = BomDetailView.as_view()(
            request, matnr="A02006000027", werks="3011", stlan="1", stlal="01",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["stlnr"], "00043885")
        self.assertEqual(get_bom.call_args.kwargs["datuv"].isoformat(), "2026-10-15")


class BomWriteApiTest(SimpleTestCase):
    @patch("app_sap_services.api.views.create_bom")
    def test_create_returns_messages(self, create):
        create.return_value = [{
            "type": "S", "id": "", "number": 0, "text": "成功", "row": 0, "field": None,
        }]
        request = _auth(factory.post(
            "/api/sap/boms/",
            {
                "matnr": "A02006000027",
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "lines": [_LINE],
            },
            format="json",
        ))
        response = BomListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["matnr"], "A02006000027")
        self.assertEqual(response.data["messages"][0]["type"], "S")

    @patch("app_sap_services.api.views.create_bom")
    def test_maintain_failure_is_400(self, create):
        create.side_effect = BomMaintainError([
            {"type": "E", "id": "M3", "number": 1, "text": "组件不存在", "row": 1, "field": "IDNRK"},
            {"type": "W", "id": "", "number": 2, "text": "注意", "row": None, "field": None},
        ])
        request = _auth(factory.post(
            "/api/sap/boms/",
            {
                "matnr": "A02006000027",
                "werks": "3011",
                "stlan": "1",
                "stlal": "01",
                "lines": [_LINE],
            },
            format="json",
        ))
        response = BomListCreateView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "sap_business")
        self.assertEqual(response.data["detail"], "组件不存在")
        self.assertEqual(len(response.data["messages"]), 2)

    @patch("app_sap_services.api.views.update_bom")
    def test_put_uses_url_key(self, update):
        update.return_value = [{
            "type": "S", "id": "", "number": 0, "text": "成功", "row": 0, "field": None,
        }]
        request = _auth(factory.put(
            "/api/sap/boms/A02006000027/3011/1/01/",
            {
                "matnr": "OTHER",
                "werks": "9999",
                "stlan": "9",
                "stlal": "99",
                "lines": [_LINE],
            },
            format="json",
        ))
        response = BomDetailView.as_view()(
            request, matnr="A02006000027", werks="3011", stlan="1", stlal="01",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.kwargs["matnr"], "A02006000027")
        self.assertEqual(update.call_args.kwargs["werks"], "3011")
        self.assertEqual(update.call_args.kwargs["stlan"], "1")
        self.assertEqual(update.call_args.kwargs["stlal"], "01")
        self.assertEqual(response.data["matnr"], "A02006000027")

    @patch("app_sap_services.api.views.delete_bom")
    def test_delete_returns_message(self, delete):
        delete.return_value = {"rtype": "S", "rtmsg": "删除成功"}
        request = _auth(factory.delete("/api/sap/boms/A02006000027/3011/1/01/"))
        response = BomDetailView.as_view()(
            request, matnr="A02006000027", werks="3011", stlan="1", stlal="01",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["rtype"], "S")
        self.assertEqual(response.data["rtmsg"], "删除成功")
        delete.assert_called_once_with(
            matnr="A02006000027", werks="3011", stlan="1", stlal="01",
        )
