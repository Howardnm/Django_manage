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
    # 1. 初始化 AnyIO 内存流
    read_from_client_send, read_from_client_receive = anyio.create_memory_object_stream(100)
    write_from_server_send, write_from_server_receive = anyio.create_memory_object_stream(100)
    
    # 2. 注册会话到管理中心
    session_manager.register_session(session_id, read_from_client_send)

    # 3. 发送首个 'endpoint' 事件给 AI Agent，告知消息提交地址
    messages_url = request.build_absolute_uri("../messages/") + f"?sessionId={session_id}"
    yield f"event: endpoint\ndata: {messages_url}\n\n"
    
    # 4. 异步运行 MCP Server 任务
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

    try:
        # 5. 将 Server 写出的消息转发给 SSE 客户端
        async with write_from_server_receive:
            async for message in write_from_server_receive:
                if isinstance(message, Exception):
                    logger.error(f"MCP Protocol Exception: {message}")
                    break
                
                # 解包包装类并序列化
                inner = getattr(message, "message", message)
                if hasattr(inner, "model_dump_json"):
                    json_payload = inner.model_dump_json()
                else:
                    json_payload = mcp_json_dumps(inner)
                
                yield f"event: message\ndata: {json_payload}\n\n"
    except Exception as e:
        logger.error(f"SSE stream error for session {session_id}: {str(e)}")
    finally:
        server_task.cancel()
        session_manager.unregister_session(session_id)
        logger.info(f"MCP Session {session_id} cleanup complete.")
