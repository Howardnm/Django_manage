"""
SAP RFC 连接管理器 —— 线程安全 + DLL 引导 + 自动重连。

使用 threading.local 为每个线程维护独立 pyrfc 连接，
避免跨线程共享导致的段错误。

用法:
    mgr = ConnectionManager(config)
    result = mgr.call_rfc('ZRFC_MATERIAL_MESN', MAT_RANGE=[...])
"""

import os
import time
import threading
import logging

from .config import SAPConfig
from .exceptions import SAPConnectionError, SAPRfcError

logger = logging.getLogger('sap.connection')

_bootstrap_lock = threading.Lock()
_pyrfc_bootstrapped = False


def _import_pyrfc():
    """
    延迟导入 pyrfc（必须在 _bootstrap_pyrfc() 之后调用）。

    返回 pyrfc.Connection 类，不依赖模块级全局变量。
    Python import 缓存确保多次调用无副作用。
    """
    from pyrfc import Connection
    return Connection


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
            os.add_dll_directory(sap_lib_path)
            os.environ['PATH'] = sap_lib_path + os.pathsep + os.environ.get('PATH', '')
        else:
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
    - call_rfc() 统一入口，封装连接获取/释放/异常转换
    """

    def __init__(self, config: SAPConfig):
        _bootstrap_pyrfc(config.sap_lib_path)
        self._Connection = _import_pyrfc()

        self._conn_params = config.to_connection_params()
        self._max_idle_seconds = config.max_idle_seconds
        self._max_retries = config.max_retries
        self._retry_delay = config.retry_delay
        self._local = threading.local()

    # =========================================================================
    # 连接生命周期
    # =========================================================================

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

    def release_connection(self):
        """标记连接为闲置（不立即关闭，由过期机制处理）"""
        self._local.last_used = time.time()

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

    def _create_connection(self):
        """创建新 SAP 连接（带重试 + 指数退避）"""
        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                conn = self._Connection(**self._conn_params)
                conn.ping()
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

    # =========================================================================
    # RFC 调用
    # =========================================================================

    def call_rfc(self, function_name: str, **params):
        """
        执行 RFC 调用 —— 统一入口。

        封装连接获取、释放、异常转换，消除 builder/gateway 中的重复代码。

        Args:
            function_name: RFC 函数名
            **params: pyrfc 调用参数

        Returns:
            SAP 返回的原始字典

        Raises:
            SAPRfcError: RFC 调用失败时
        """
        conn = None
        try:
            conn = self.get_connection()
            logger.debug(
                f"RFC 调用: {function_name}, params: {list(params.keys())}"
            )
            result = conn.call(function_name, **params)
            logger.info(f"RFC 调用成功: {function_name}")
            return result
        except SAPRfcError:
            raise
        except Exception as e:
            raise SAPRfcError(
                function=function_name,
                message=str(e),
                params={k: str(v)[:200] for k, v in params.items()},
            ) from e
        finally:
            if conn:
                self.release_connection()

    # =========================================================================
    # 健康检查
    # =========================================================================

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
