"""
SAP RFC 连接管理器 —— 线程安全 + DLL 引导 + 自动重连。

使用 threading.local 为每个线程维护独立 pyrfc 连接，
避免跨线程共享导致的段错误。

用法:
    mgr = ConnectionManager(config)
    with mgr.connection() as conn:
        result = conn.call('ZRFC_MATERIAL_MESN', ...)
"""

import os
import time
import threading
import logging

from .config import SAPConfig
from .exceptions import SAPConnectionError

logger = logging.getLogger('sap.connection')

# 模块级 DLL 引导锁——确保只初始化一次
_bootstrap_lock = threading.Lock()
_pyrfc_bootstrapped = False


def _bootstrap_pyrfc(sap_lib_path: str):
    """
    pyrfc DLL 引导 —— 必须在 import pyrfc 之前执行。

    1. os.add_dll_directory() 解决 Python 3.8+ 找不到主 DLL 的问题
    2. PATH 环境变量追加 lib 路径，解决 SAP ICU(多语言) 依赖问题
    """
    global _pyrfc_bootstrapped
    if _pyrfc_bootstrapped:
        return

    with _bootstrap_lock:
        if _pyrfc_bootstrapped:
            return

        if not os.path.isdir(sap_lib_path):
            raise SAPConnectionError(
                f"SAP NW RFC SDK lib 路径不存在: {sap_lib_path}\n"
                f"请在 Django settings 中检查 SAP_SERVICES_CONFIG['sap_lib_path']"
            )

        if os.name == 'nt':
            # Windows: DLL 目录注册 + PATH 追加，解决 ICU 依赖查找问题
            os.add_dll_directory(sap_lib_path)
            os.environ['PATH'] = sap_lib_path + os.pathsep + os.environ.get('PATH', '')
        else:
            # Linux: LD_LIBRARY_PATH 由 Dockerfile 设置，此处仅校验路径
            os.environ['LD_LIBRARY_PATH'] = (
                sap_lib_path + os.pathsep + os.environ.get('LD_LIBRARY_PATH', '')
            )
        _pyrfc_bootstrapped = True
        logger.info(f"SAP NW RFC SDK 初始化完成: {sap_lib_path}")


class ConnectionManager:
    """
    线程安全的 SAP RFC 连接管理。

    特性:
    - 每个线程独立连接 (threading.local), 避免跨线程段错误
    - 连接闲置超时自动重建
    - 连接失败自动重试（指数退避）
    - 支持上下文管理器: with mgr.connection() as conn: ...
    """

    def __init__(self, config: SAPConfig):
        _bootstrap_pyrfc(config.sap_lib_path)
        # 延时导入 pyrfc，确保 DLL 已引导
        global Connection, RFCError
        from pyrfc import Connection, RFCError

        self._conn_params = config.to_connection_params()
        self._max_idle_seconds = config.max_idle_seconds
        self._max_retries = config.max_retries
        self._retry_delay = config.retry_delay
        self._local = threading.local()

    def get_connection(self):
        """
        获取当前线程的 SAP 连接。

        - 首次调用：创建新连接
        - 后续调用：复用已有连接
        - 连接过期/断开：自动重建
        """
        conn = getattr(self._local, 'connection', None)
        last_used = getattr(self._local, 'last_used', 0)

        now = time.time()
        if conn is None or (now - last_used > self._max_idle_seconds):
            conn = self._create_connection()
            self._local.connection = conn

        self._local.last_used = now
        return conn

    def release_connection(self, conn=None):
        """标记连接为闲置（不立即关闭，由过期机制处理）"""
        self._local.last_used = time.time()

    def _create_connection(self):
        """创建新 SAP 连接（带重试 + 指数退避）"""
        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                conn = Connection(**self._conn_params)
                conn.ping()  # 健康检查
                logger.info(
                    f"SAP 连接建立成功 "
                    f"(ashost={self._conn_params.get('ashost')}, "
                    f"client={self._conn_params.get('client')}, "
                    f"attempt={attempt})"
                )
                return conn
            except Exception as e:
                last_error = e
                logger.warning(f"SAP 连接失败 (attempt={attempt}/{self._max_retries}): {e}")
                if attempt < self._max_retries:
                    time.sleep(self._retry_delay * attempt)

        raise SAPConnectionError(
            f"无法建立 SAP 连接，已重试 {self._max_retries} 次: {last_error}"
        )

    def connection(self):
        """上下文管理器: with mgr.connection() as conn: ..."""
        return _ConnectionContext(self)

    def close(self):
        """关闭当前线程的 SAP 连接"""
        conn = getattr(self._local, 'connection', None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
            self._local.connection = None
            logger.debug("已关闭当前线程的 SAP 连接")

    def health_check(self) -> dict:
        """健康检查：返回连接状态"""
        try:
            conn = self.get_connection()
            conn.ping()
            return {
                'status': 'healthy',
                'ashost': self._conn_params.get('ashost'),
                'client': self._conn_params.get('client'),
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}


class _ConnectionContext:
    """轻量上下文管理器，支持 with mgr.connection() as conn 语法"""

    def __init__(self, manager: ConnectionManager):
        self._mgr = manager
        self._conn = None

    def __enter__(self):
        self._conn = self._mgr.get_connection()
        return self._conn

    def __exit__(self, *args):
        self._mgr.release_connection(self._conn)
