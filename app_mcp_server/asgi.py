"""MCP Streamable HTTP ASGI：鉴权、CORS、session lifespan。

必须在 Django `get_asgi_application()` 之后再 import 本模块
（tools 在 AppConfig.ready 里注册，session_manager 在此创建）。
"""
import secrets
from contextlib import asynccontextmanager

from django.conf import settings as django_settings
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

from app_mcp_server.core.server import mcp

# Creates session_manager. Nested lifespan is not used; the host app runs it.
mcp.streamable_http_app(
    streamable_http_path="/mcp",
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

MCP_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": (
        "Content-Type, Authorization, "
        "Mcp-Session-Id, Mcp-Protocol-Version, Mcp-Method, Mcp-Name, Last-Event-ID"
    ),
    "Access-Control-Expose-Headers": "Mcp-Session-Id",
}

MCP_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]

_WWW_AUTHENTICATE = 'Bearer realm="mcp", error="invalid_token"'


def _bearer_token(authorization: str | None) -> str | None:
    """RFC 6750：从 `Authorization: Bearer <token>` 取出 token。"""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or " " in token.strip():
        return None
    return token.strip() or None


def _token_matches(token: str, expected: str) -> bool:
    if len(token) != len(expected):
        secrets.compare_digest(expected, expected)
        return False
    return secrets.compare_digest(token, expected)


class MCPASGIApp:
    """ASGI wrapper: Bearer auth + CORS around StreamableHTTPSessionManager."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        request = Request(scope, receive)

        if request.method == "OPTIONS":
            response = Response(status_code=204, headers=MCP_CORS_HEADERS)
            await response(scope, receive, send)
            return

        expected_key = getattr(django_settings, "MCP_API_KEY", None) or None
        if expected_key:
            token = _bearer_token(request.headers.get("authorization"))
            if token is None or not _token_matches(token, expected_key):
                response = JSONResponse(
                    {"error": "invalid_token", "error_description": "Authentication Required"},
                    status_code=401,
                    headers={**MCP_CORS_HEADERS, "WWW-Authenticate": _WWW_AUTHENTICATE},
                )
                await response(scope, receive, send)
                return

        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in MCP_CORS_HEADERS.items():
                    headers[key] = value
            await send(message)

        await mcp.session_manager.handle_request(scope, receive, send_with_cors)


mcp_asgi = MCPASGIApp()


@asynccontextmanager
async def mcp_lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield
