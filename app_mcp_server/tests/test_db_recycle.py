"""MCP 在请求周期外回收数据库连接。不连真实 MySQL。"""
from unittest import mock

from django.db import OperationalError
from django.test import SimpleTestCase

from app_mcp_server.auth import JwtAuthError, authenticate_http
from app_mcp_server.db import recycle_db_connections
from app_mcp_server.responses import safe_tool
from app_mcp_server.tests.test_jwt_auth import _asgi_call, _starlette_request


class RecycleDbConnectionsTests(SimpleTestCase):
    def test_skips_while_a_connection_is_inside_a_transaction(self):
        conn = mock.Mock(in_atomic_block=True)
        with (
            mock.patch("app_mcp_server.db.connections") as connections,
            mock.patch("app_mcp_server.db.close_old_connections") as close,
        ):
            connections.all.return_value = [conn]
            recycle_db_connections()
        close.assert_not_called()

    def test_closes_stale_connections_outside_a_transaction(self):
        conn = mock.Mock(in_atomic_block=False)
        with (
            mock.patch("app_mcp_server.db.connections") as connections,
            mock.patch("app_mcp_server.db.close_old_connections") as close,
        ):
            connections.all.return_value = [conn]
            recycle_db_connections()
        close.assert_called_once_with()

    def test_swallows_close_failure_and_drops_the_connection(self):
        conn = mock.Mock(in_atomic_block=False)
        conn.connection = object()
        with (
            mock.patch("app_mcp_server.db.connections") as connections,
            mock.patch(
                "app_mcp_server.db.close_old_connections",
                side_effect=OperationalError("4031"),
            ),
        ):
            connections.all.return_value = [conn]
            recycle_db_connections()
        self.assertIsNone(conn.connection)


class RecycleCallSiteTests(SimpleTestCase):
    def test_authenticate_http_recycles_on_the_way_in_and_out(self):
        with mock.patch("app_mcp_server.auth.recycle_db_connections") as recycle:
            with self.assertRaises(JwtAuthError):
                authenticate_http(_starlette_request())
        self.assertEqual(recycle.call_count, 2)

    def test_safe_tool_recycles_even_when_the_tool_crashes(self):
        @safe_tool
        def tool():
            raise RuntimeError("boom")

        with mock.patch("app_mcp_server.db.recycle_db_connections") as recycle:
            result = tool()
        self.assertIs(result["ok"], False)
        self.assertEqual(result["error_code"], "INTERNAL")
        self.assertEqual(recycle.call_count, 2)

    def test_auth_database_error_is_503(self):
        with mock.patch(
            "app_mcp_server.asgi.authenticate_http",
            side_effect=OperationalError("4031"),
        ):
            status, headers, body = _asgi_call(
                "POST", {"authorization": "Bearer mcp_dead"},
            )
        self.assertEqual(status, 503)
        self.assertIn(b"temporarily_unavailable", body)
        self.assertIn("access-control-allow-origin", headers)
