import json
import logging
from mcp.types import JSONRPCMessage
from ..core.sessions import session_manager, IncomingMessage

logger = logging.getLogger("app_mcp_server.transports.http")

async def process_mcp_message(session_id: str, request_body: bytes) -> bool:
    """
    接收来自 AI Agent 的 POST 消息并路由到正确的 MCP 会话流。
    """
    session_stream = session_manager.get_session_stream(session_id)
    if not session_stream:
        logger.warning(f"Message received for inactive session: {session_id}")
        return False

    try:
        # 1. 解析 JSON-RPC 消息
        body_data = json.loads(request_body.decode('utf-8'))
        
        # 2. 包装并验证消息，符合 SDK 内部 SessionMessage 结构要求
        rpc_message = JSONRPCMessage.model_validate(body_data)
        wrapped_msg = IncomingMessage(message=rpc_message, metadata={})
        
        # 3. 发送给该会话对应的读入端流
        await session_stream.send(wrapped_msg)
        return True
        
    except Exception as e:
        logger.error(f"Failed to process MCP message for session {session_id}: {str(e)}", exc_info=True)
        raise e
