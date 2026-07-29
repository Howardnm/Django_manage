import uuid
import anyio
import logging
import time
from typing import Dict, Optional, Any
from mcp.types import JSONRPCMessage

logger = logging.getLogger(__name__)

# 模拟 SDK 内部的消息包装结构
class IncomingMessage:
    def __init__(self, message: JSONRPCMessage, metadata: Optional[Dict[str, Any]] = None):
        self.message = message
        self.metadata = metadata or {}

class SessionManager:
    """管理活跃的 MCP 会话，并提供过时检测能力"""
    def __init__(self):
        # session_id -> {stream: stream, last_active: timestamp}
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self) -> str:
        """生成唯一会话 ID"""
        return str(uuid.uuid4())

    def register_session(self, session_id: str, send_stream: anyio.abc.ObjectSendStream):
        """记录会话及其流"""
        self._sessions[session_id] = {
            "stream": send_stream,
            "last_active": time.time()
        }
        logger.debug(f"MCP Session registered: {session_id}")

    def update_activity(self, session_id: str):
        """更新最后活跃时间，延长生命周期"""
        if session_id in self._sessions:
            self._sessions[session_id]["last_active"] = time.time()

    def unregister_session(self, session_id: str):
        """显式清理会话"""
        if session_id in self._sessions:
            self._sessions.pop(session_id)
            logger.info(f"MCP Session {session_id} removed from manager.")

    def get_session_stream(self, session_id: str) -> Optional[anyio.abc.ObjectSendStream]:
        """获取流并更新活跃度"""
        session_info = self._sessions.get(session_id)
        if session_info:
            session_info["last_active"] = time.time()
            return session_info["stream"]
        return None

    def clean_stale_sessions(self, timeout_seconds: int = 3600):
        """
        清理超过 1 小时未活跃的会话 (防止内存泄漏)
        建议由 Celery 任务或中间件定时触发
        """
        now = time.time()
        stale_ids = [
            sid for sid, info in self._sessions.items()
            if now - info["last_active"] > timeout_seconds
        ]
        for sid in stale_ids:
            self.unregister_session(sid)
            logger.warning(f"Stale MCP session {sid} cleaned up automatically.")

# 导出全局单例
session_manager = SessionManager()
