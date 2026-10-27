"""物料描述查询。不连 SAP。"""

from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from app_sap_services.api.views import MaterialNameView
from app_sap_services.query.gateway import SAPGateway
from app_sap_services.selectors.material import material_names

from .helpers import FakeConnMgr


factory = APIRequestFactory()


class _User:
    is_authenticated = True
    is_active = True


def _auth(request):
    force_authenticate(request, user=_User())
    return request


def _zmarc(*rows):
    return {"ZMARC": list(rows)}


class MaterialNamesTest(SimpleTestCase):
    def test_each_code_is_one_exact_call_and_connection_closes(self):
        conn = FakeConnMgr(responses=[
            _zmarc(
                {"MATNR": "A01002000009", "WERKS": "3011", "MAKTX": ""},
                {"MATNR": "A01002000009", "WERKS": "3012", "MAKTX": "ABS 121H"},
            ),
            _zmarc(),
        ])
        with patch("app_sap_services.selectors.material.sap", SAPGateway(conn)):
            names = material_names(["A01002000009", "A01002000011"])
        self.assertEqual(names, {
            "A01002000009": "ABS 121H",
            "A01002000011": "",
        })
        self.assertEqual(len(conn.calls), 2)
        self.assertEqual(conn.calls[0][0], "ZRFC_MATERIAL_MESN")
        self.assertEqual(conn.calls[0][1]["MAT_RANGE"], [{
            "SIGN": "I", "OPTION": "EQ", "LOW": "A01002000009", "HIGH": "",
        }])
        self.assertEqual(conn.calls[1][1]["MAT_RANGE"][0]["LOW"], "A01002000011")
        self.assertEqual(conn.closed, 1)

    def test_failure_still_closes_the_connection(self):
        class _Boom(FakeConnMgr):
            def call_rfc(self, function_name, **params):
                super().call_rfc(function_name, **params)
                raise RuntimeError("sap down")

        conn = _Boom()
        with patch("app_sap_services.selectors.material.sap", SAPGateway(conn)):
            with self.assertRaises(RuntimeError):
                material_names(["A01002000009"])
        self.assertEqual(conn.closed, 1)


class MaterialNameApiTest(SimpleTestCase):
    def test_anonymous_is_forbidden(self):
        request = factory.get("/api/sap/materials/", {"matnr": "A01002000009"})
        response = MaterialNameView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["code"], "not_authenticated")

    def test_missing_matnr_is_400(self):
        request = _auth(factory.get("/api/sap/materials/"))
        response = MaterialNameView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")

    @patch("app_sap_services.api.views.material_names")
    def test_returns_every_requested_code(self, named):
        named.return_value = {
            "A01002000009": "ABS 121H",
            "A01002000011": "",
        }
        request = _auth(factory.get("/api/sap/materials/", {
            "matnr": ["A01002000009", "A01002000011"],
        }))
        response = MaterialNameView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [
            {"matnr": "A01002000009", "maktx": "ABS 121H"},
            {"matnr": "A01002000011", "maktx": ""},
        ])
        named.assert_called_once_with(["A01002000009", "A01002000011"])

    def test_too_many_codes_is_400(self):
        codes = [f"A{i:011d}" for i in range(41)]
        request = _auth(factory.get("/api/sap/materials/", {"matnr": codes}))
        response = MaterialNameView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "validation_error")
