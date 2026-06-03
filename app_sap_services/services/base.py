"""SAP RFC 调用基类 — 封装 pyrfc 调用与错误处理"""

import logging
import time
from functools import wraps

from ..utils.exceptions import SapRfcError, SapConnectionError

logger = logging.getLogger('app_sap_services')


def _retry_on_reconnect(func):
    """连接断开时自动重连一次"""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except SapConnectionError:
            logger.warning("SAP 连接已断开，尝试重连...")
            self._close_connection()
            return func(self, *args, **kwargs)
    return wrapper


class SapBaseService:
    """所有 SAP RFC 服务的基类"""

    def __init__(self):
        from .connection import connection_pool
        self._pool = connection_pool
        # 子类可定义的 SAP RFC 函数名
        self.function_module = ''

    # ── 连接管理 ──────────────────────────────────────────

    def _get_connection(self):
        return self._pool.get_connection()

    def _close_connection(self):
        self._pool.close()

    # ── RFC 调用 ──────────────────────────────────────────

    @_retry_on_reconnect
    def _call_rfc(self, function_name: str, **params):
        """调用 SAP RFC 函数并返回完整结果字典"""
        conn = self._get_connection()
        logger.info(f"SAP RFC → {function_name}({list(params.keys())})")
        start = time.perf_counter()
        try:
            result = conn.call(function_name, **params)
            elapsed = time.perf_counter() - start
            logger.info(f"SAP RFC ← {function_name} ({elapsed:.3f}s)")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            logger.error(f"SAP RFC ✗ {function_name} ({elapsed:.3f}s): {e}")
            raise SapRfcError(f"RFC调用失败 [{function_name}]: {e}") from e

    def call(self, function_name: str, **params) -> dict:
        """
        对外暴露的通用 RFC 调用入口。
        用法: service.call('BAPI_MATERIAL_GET_DETAIL', MATNUMBER='xxx')
        """
        return self._call_rfc(function_name, **params)

    def health_check(self) -> bool:
        """检查当前服务是否能连通 SAP"""
        return self._pool.health_check()
