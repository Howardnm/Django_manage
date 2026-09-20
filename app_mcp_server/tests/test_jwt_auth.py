"""MCP JWT 验签与 HTTP 401 门。"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from starlette.requests import Request

from app_mcp_server.asgi import mcp_asgi
from app_mcp_server.auth import (
    JwtAuthError,
    authenticate_http,
    clear_public_key_cache,
    get_public_key,
    resolve_user,
    verify_jwt,
)
from app_mcp_server.tests.jwt_helpers import generate_rsa_pair, make_jwt, make_unsigned_token

User = get_user_model()


def _asgi_call(method, headers=None, path="/mcp"):
    sent = []
    header_pairs = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": header_pairs,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async_to_sync(mcp_asgi)(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    resp_headers = {
        k.decode().lower(): v.decode() for k, v in start.get("headers", [])
    }
    return start["status"], resp_headers, body


def _starlette_request(authorization=None):
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    return Request(scope)


class JwtVerifyTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = generate_rsa_pair()
        cls.other_private, _ = generate_rsa_pair()

    def setUp(self):
        clear_public_key_cache()
        self.settings_ctx = override_settings(
            MCP_JWT_PUBLIC_KEY=self.public_pem,
            MCP_JWT_PUBLIC_KEY_PATH="",
            MCP_JWT_LEEWAY=30,
        )
        self.settings_ctx.enable()
        clear_public_key_cache()

    def tearDown(self):
        self.settings_ctx.disable()
        clear_public_key_cache()

    def test_valid_rs256_jwt(self):
        token = make_jwt(self.private_pem, sub="E001", employeeNo="E001")
        payload = verify_jwt(token)
        self.assertEqual(payload["sub"], "E001")

    def test_accepts_any_issuer_and_audience(self):
        token = make_jwt(self.private_pem, iss="other-iss", aud="other-aud")
        payload = verify_jwt(token)
        self.assertEqual(payload["iss"], "other-iss")
        self.assertEqual(payload["aud"], "other-aud")

    def test_rejects_alg_none(self):
        with self.assertRaises(JwtAuthError):
            verify_jwt(make_unsigned_token(sub="E001"))

    def test_rejects_hs256(self):
        token = make_jwt("not-used", alg="HS256", sub="E001")
        with self.assertRaises(JwtAuthError):
            verify_jwt(token)

    def test_rejects_expired(self):
        token = make_jwt(
            self.private_pem,
            exp=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        with self.assertLogs("app_mcp_server.auth", level="WARNING") as cm:
            with self.assertRaises(JwtAuthError):
                verify_jwt(token)
        self.assertTrue(any("expired" in line for line in cm.output))

    def test_rejects_missing_sub(self):
        token = make_jwt(self.private_pem, drop=("sub",))
        with self.assertRaises(JwtAuthError):
            verify_jwt(token)

    def test_rejects_wrong_key(self):
        token = make_jwt(self.other_private, sub="E001")
        with self.assertRaises(JwtAuthError):
            verify_jwt(token)

    def test_empty_public_key_fails_closed(self):
        with override_settings(MCP_JWT_PUBLIC_KEY="", MCP_JWT_PUBLIC_KEY_PATH=""):
            clear_public_key_cache()
            self.assertEqual(get_public_key(), "")
            with self.assertRaises(JwtAuthError):
                verify_jwt(make_jwt(self.private_pem))
        clear_public_key_cache()

    def test_path_overrides_key(self):
        fd, path = tempfile.mkstemp(suffix=".pem")
        os.write(fd, self.public_pem.encode())
        os.close(fd)
        try:
            with override_settings(
                MCP_JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nnot-the-key\n-----END PUBLIC KEY-----",
                MCP_JWT_PUBLIC_KEY_PATH=path,
            ):
                clear_public_key_cache()
                self.assertEqual(get_public_key().strip(), self.public_pem.strip())
                payload = verify_jwt(make_jwt(self.private_pem, sub="E001"))
                self.assertEqual(payload["sub"], "E001")
        finally:
            os.unlink(path)
            clear_public_key_cache()

    def test_missing_path_fails_closed(self):
        with override_settings(MCP_JWT_PUBLIC_KEY_PATH="/no/such/mcp-jwt.pem"):
            clear_public_key_cache()
            self.assertEqual(get_public_key(), "")
            with self.assertRaises(JwtAuthError):
                verify_jwt(make_jwt(self.private_pem))
        clear_public_key_cache()


class JwtResolveUserTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="alice", email="alice@corp.com", password="x",
            employee_no="E001",
        )
        cls.other = User.objects.create_user(
            username="bob", email="bob@corp.com", password="x",
            employee_no="E002",
        )
        cls.inactive = User.objects.create_user(
            username="old", email="old@corp.com", password="x",
            employee_no="E003", is_active=False,
        )
        cls.legacy = User.objects.create_user(
            username="0604019", email="legacy@corp.com", password="x",
        )

    def test_email_case_and_space(self):
        user = resolve_user({"email": " Alice@Corp.com ", "employeeNo": "E002"})
        self.assertEqual(user.pk, self.user.pk)

    def test_email_present_but_unknown_does_not_fallback(self):
        with self.assertLogs("app_mcp_server.auth", level="WARNING") as cm:
            with self.assertRaises(JwtAuthError):
                resolve_user({"email": "nobody@corp.com", "employeeNo": "E001", "sub": "E001"})
        self.assertTrue(any("nobody@corp.com" in line for line in cm.output))
        self.assertTrue(any("no employeeNo/sub fallback" in line for line in cm.output))

    def test_employee_no_fallback_when_email_null(self):
        user = resolve_user({"email": None, "employeeNo": "E001", "sub": "other"})
        self.assertEqual(user.pk, self.user.pk)

    def test_employee_no_does_not_match_username(self):
        with self.assertRaises(JwtAuthError):
            resolve_user({"email": None, "employeeNo": "0604019", "sub": "other"})

    def test_real_employee_no_when_email_null(self):
        self.user.employee_no = "0604019"
        self.user.save()
        user = resolve_user({"email": None, "employeeNo": "0604019", "sub": "0604019"})
        self.assertEqual(user.pk, self.user.pk)

    def test_sub_matches_employee_no_then_username(self):
        user = resolve_user({"email": "", "sub": "E002"})
        self.assertEqual(user.pk, self.other.pk)

    def test_sub_falls_back_to_username(self):
        user = resolve_user({"email": "", "sub": "0604019"})
        self.assertEqual(user.pk, self.legacy.pk)

    def test_inactive_user_rejected(self):
        with self.assertRaises(JwtAuthError):
            resolve_user({"email": "old@corp.com"})

    def test_unknown_user_rejected(self):
        with self.assertLogs("app_mcp_server.auth", level="WARNING") as cm:
            with self.assertRaises(JwtAuthError):
                resolve_user({"employeeNo": "NOPE", "sub": "NOPE"})
        self.assertTrue(any("unknown employeeNo=NOPE" in line for line in cm.output))


class JwtHttpGateTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.private_pem, cls.public_pem = generate_rsa_pair()

    def setUp(self):
        clear_public_key_cache()
        self.settings_ctx = override_settings(
            MCP_JWT_PUBLIC_KEY=self.public_pem,
            MCP_JWT_PUBLIC_KEY_PATH="",
            MCP_JWT_LEEWAY=30,
        )
        self.settings_ctx.enable()
        clear_public_key_cache()
        self.user = User.objects.create_user(
            username="alice", email="alice@corp.com", password="x",
            employee_no="E001",
        )

    def tearDown(self):
        self.settings_ctx.disable()
        clear_public_key_cache()

    def test_options_is_204_without_token(self):
        status, headers, _ = _asgi_call("OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(headers.get("access-control-allow-origin"), "*")

    def test_missing_token_401(self):
        status, headers, body = _asgi_call("POST")
        self.assertEqual(status, 401)
        self.assertIn("bearer", headers.get("www-authenticate", "").lower())
        payload = json.loads(body)
        self.assertEqual(payload["error"], "invalid_token")
        self.assertNotIn("expired", body.decode().lower())
        self.assertNotIn("signature", body.decode().lower())

    def test_legacy_api_key_no_longer_accepted(self):
        status, _, _ = _asgi_call(
            "POST", {"Authorization": "Bearer legacy-shared-secret"},
        )
        self.assertEqual(status, 401)

    def test_bad_token_401_generic(self):
        status, _, body = _asgi_call("POST", {"Authorization": "Bearer not-a-jwt"})
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")

    def test_unknown_user_same_401_body(self):
        token = make_jwt(
            self.private_pem, sub="NOPE", employeeNo="NOPE", email="nope@corp.com",
        )
        status, _, body = _asgi_call("POST", {"Authorization": f"Bearer {token}"})
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")

    def test_authenticate_http_sets_state(self):
        token = make_jwt(
            self.private_pem,
            sub="E001",
            employeeNo="E001",
            email="alice@corp.com",
            tool="search_projects",
        )
        request = _starlette_request(f"Bearer {token}")
        user = authenticate_http(request)
        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(request.state.mcp_user_id, self.user.pk)
        self.assertEqual(request.state.mcp_jwt["tool"], "search_projects")

    def test_empty_public_key_http_401(self):
        with override_settings(MCP_JWT_PUBLIC_KEY="", MCP_JWT_PUBLIC_KEY_PATH=""):
            clear_public_key_cache()
            token = make_jwt(self.private_pem, email="alice@corp.com")
            status, _, _ = _asgi_call("POST", {"Authorization": f"Bearer {token}"})
            self.assertEqual(status, 401)
        clear_public_key_cache()


class McpApiKeyHttpGateTests(TestCase):
    def setUp(self):
        from datetime import timedelta

        from django.utils import timezone

        from app_user.services.mcp_api_key import generate_mcp_api_key

        self.user = User.objects.create_user(
            username="keyuser", email="keyuser@corp.com", password="x",
            mcp_api_key_enabled=True,
        )
        self.plain = generate_mcp_api_key(self.user)
        self.timezone = timezone
        self.timedelta = timedelta

    def test_valid_api_key_sets_state(self):
        from app_mcp_server.auth import authenticate_http

        request = _starlette_request(f"Bearer {self.plain}")
        user = authenticate_http(request)
        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(request.state.mcp_user_id, self.user.pk)
        self.assertEqual(request.state.mcp_jwt["auth"], "api_key")

    def test_unknown_api_key_401(self):
        status, _, body = _asgi_call(
            "POST", {"Authorization": "Bearer mcp_this_is_not_a_real_key_value_xx"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")

    def test_expired_api_key_401(self):
        self.user.mcp_api_key_expires_at = self.timezone.now() - self.timedelta(days=1)
        self.user.save(update_fields=["mcp_api_key_expires_at"])
        status, _, body = _asgi_call(
            "POST", {"Authorization": f"Bearer {self.plain}"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")

    def test_disabled_api_key_401(self):
        self.user.mcp_api_key_enabled = False
        self.user.save(update_fields=["mcp_api_key_enabled"])
        status, _, body = _asgi_call(
            "POST", {"Authorization": f"Bearer {self.plain}"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")

    def test_refresh_invalidates_old_key(self):
        from app_user.services.mcp_api_key import generate_mcp_api_key

        generate_mcp_api_key(self.user)
        status, _, body = _asgi_call(
            "POST", {"Authorization": f"Bearer {self.plain}"},
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "invalid_token")
