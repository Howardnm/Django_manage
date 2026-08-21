import asyncio
import logging
import anyio
from typing import AsyncGenerator
from mcp.server import NotificationOptions
from mcp.server.models import InitializationOptions
from ..core.server import mcp_server, mcp_json_dumps
from ..core.sessions import session_manager

logger = logging.getLogger(__name__)

async def mcp_sse_generator(request, session_id: str) -> AsyncGenerator[str, None]:
    """
    生成符合 MCP 规范的 SSE 事件流，支持针对非标准 Nginx 代理的 Host 修复。
    """
    # 1. 初始化流
    read_from_client_send, read_from_client_receive = anyio.create_memory_object_stream(100)
    write_from_server_send, write_from_server_receive = anyio.create_memory_object_stream(100)
    
    # 2. 注册会话
    session_manager.register_session(session_id, read_from_client_send)

    # 3. 构造消息 URL (处理特殊 Nginx 反代配置)
    # 优先检测您 Nginx 发送的自定义 X-Host 字段
    custom_host = request.headers.get('X-Host')
    if custom_host:
        host = custom_host
    else:
        host = request.get_host()
    
    # 检测协议 (识别您的 X-Scheme)
    scheme = 'https' if request.is_secure() or request.headers.get('X-Scheme') == 'https' else 'http'
    
    # 确保路径拼接正确
    # 将当前的 /mcp/sse/ 路径替换为 /mcp/messages/
    base_path = request.path.replace('/sse/', '/messages/')
    messages_url = f"{base_path}?sessionId={session_id}"
    
    logger.info(f"SSE [{session_id}]: Relative Endpoint URL: {messages_url}")

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
