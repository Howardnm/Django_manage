"""
ASGI config for Django_manage project.

MCP Streamable HTTP is mounted at /mcp (official mcp SDK, not Django urls.py).
The rest of the site is served by Django.
"""

import os
from contextlib import asynccontextmanager

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import Receive, Scope, Send

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Django_manage.settings')

django_asgi = get_asgi_application()

from django.conf import settings as django_settings  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from app_mcp_server.core.server import mcp  # noqa: E402

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
        "Content-Type, X-MCP-API-KEY, Authorization, "
        "Mcp-Session-Id, Mcp-Protocol-Version, Mcp-Method, Mcp-Name, Last-Event-ID"
    ),
    "Access-Control-Expose-Headers": "Mcp-Session-Id",
}

MCP_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]


class MCPASGIApp:
    """ASGI wrapper: API-key auth + CORS around StreamableHTTPSessionManager."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return

        request = Request(scope, receive)

        if request.method == "OPTIONS":
            response = Response(status_code=204, headers=MCP_CORS_HEADERS)
            await response(scope, receive, send)
            return

        expected_key = getattr(django_settings, "MCP_API_KEY", None) or None
        if expected_key and request.headers.get("x-mcp-api-key") != expected_key:
            response = JSONResponse(
                {"error": "Authentication Required"},
                status_code=403,
                headers=MCP_CORS_HEADERS,
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
async def lifespan(app: Starlette):
    async with mcp.session_manager.run():
        yield


application = Starlette(
    routes=[
        Route("/mcp", endpoint=mcp_asgi, methods=MCP_METHODS),
        Route("/mcp/", endpoint=mcp_asgi, methods=MCP_METHODS),
        Mount("/", app=django_asgi),
    ],
    lifespan=lifespan,
)
