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

    # 3. 发送首个 'endpoint' 事件给 AI Agent
    messages_url = request.build_absolute_uri("../messages/") + f"?sessionId={session_id}"
    logger.info(f"SSE [{session_id}]: Client connected. Endpoint: {messages_url}")
    yield f"event: endpoint\ndata: {messages_url}\n\n"
    
    # 4. 启动 MCP Server 任务
    def handle_server_done(t):
        """处理任务结束，优雅忽略取消异常"""
        try:
            if not t.cancelled():
                t.result()
                logger.info(f"SSE [{session_id}]: MCP Server Task finished.")
            else:
                logger.debug(f"SSE [{session_id}]: MCP Server Task was cancelled during cleanup.")
        except Exception as e:
            logger.error(f"SSE [{session_id}]: MCP Server Task error: {e}", exc_info=True)

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
        # 5. 消息转发循环
        async with write_from_server_receive:
            async for message in write_from_server_receive:
                # 序列化逻辑
                inner = getattr(message, "message", message)
                if hasattr(inner, "model_dump_json"):
                    json_payload = inner.model_dump_json()
                else:
                    json_payload = mcp_json_dumps(inner)
                
                yield f"event: message\ndata: {json_payload}\n\n"
    except Exception as e:
        logger.warning(f"SSE [{session_id}]: Stream disconnected: {e}")
    finally:
        # 6. 清理资源
        if not server_task.done():
            server_task.cancel()
        
        # 关闭流以通知 Server 停止
        try:
            read_from_client_send.close()
        except:
            pass
            
        session_manager.unregister_session(session_id)
        logger.info(f"SSE [{session_id}]: Session cleanup complete.")
