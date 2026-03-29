import asyncio
import logging
import anyio
from typing import AsyncGenerator
from mcp.server import NotificationOptions
from mcp.server.models import InitializationOptions
from ..core.server import mcp_server, mcp_json_dumps
from ..core.sessions import session_manager

logger = logging.getLogger("app_mcp_server.transports.sse")

async def mcp_sse_generator(request, session_id: str) -> AsyncGenerator[str, None]:
    """
    生成符合 MCP 规范的 SSE 事件流。
    """
    # 1. 初始化流
    read_from_client_send, read_from_client_receive = anyio.create_memory_object_stream(100)
    write_from_server_send, write_from_server_receive = anyio.create_memory_object_stream(100)
    
    # 2. 注册会话
    session_manager.register_session(session_id, read_from_client_send)

    # 3. 构造消息 URL (处理 Nginx 反代导致 127.0.0.1 的问题)
    # 优先获取 X-Forwarded-Host 或 Host 头
    host = request.get_host() 
    scheme = 'https' if request.is_secure() or request.headers.get('X-Forwarded-Scheme') == 'https' else 'http'
    
    # 手动拼接路径，确保不再出现 127.0.0.1
    path = request.path.replace('/sse/', '/messages/')
    messages_url = f"{scheme}://{host}{path}?sessionId={session_id}"
    
    logger.info(f"SSE [{session_id}]: Final Message URL: {messages_url}")
    yield f"event: endpoint\ndata: {messages_url}\n\n"
    
    # 4. 启动 Server 任务
    def handle_server_done(t):
        try:
            if not t.cancelled():
                t.result()
        except Exception as e:
            logger.error(f"SSE [{session_id}]: Server Task error: {e}")

    server_task = asyncio.create_task(mcp_server.run(
        read_from_client_receive,
        write_from_server_send,
        InitializationOptions(
            server_name="Django_manage_HTTP_MCP",
            server_version="1.0.0",
            capabilities=mcp_server.get_capabilities(
                notification_options=NotificationOptions(),
                experimental_capabilities={},
            ),
        )
    ))
    server_task.add_done_callback(handle_server_done)

    try:
        async with write_from_server_receive:
            async for message in write_from_server_receive:
                inner = getattr(message, "message", message)
                json_payload = inner.model_dump_json() if hasattr(inner, "model_dump_json") else mcp_json_dumps(inner)
                yield f"event: message\ndata: {json_payload}\n\n"
    except Exception:
        pass
    finally:
        if not server_task.done():
            server_task.cancel()
        try:
            read_from_client_send.close()
        except:
            pass
        session_manager.unregister_session(session_id)
