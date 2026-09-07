"""
ASGI config for Django_manage project.

MCP Streamable HTTP is mounted at /mcp (official mcp SDK, not Django urls.py).
The rest of the site is served by Django.
"""

import os

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Mount, Route

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Django_manage.settings")

django_asgi = get_asgi_application()

from app_mcp_server.asgi import MCP_METHODS, mcp_asgi, mcp_lifespan  # noqa: E402

application = Starlette(
    routes=[
        Route("/mcp", endpoint=mcp_asgi, methods=MCP_METHODS),
        Route("/mcp/", endpoint=mcp_asgi, methods=MCP_METHODS),
        Mount("/", app=django_asgi),
    ],
    lifespan=mcp_lifespan,
)
