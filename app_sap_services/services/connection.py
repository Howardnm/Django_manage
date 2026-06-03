"""SAP RFC 连接池管理"""

import logging
import threading
from contextlib import contextmanager

from django.conf import settings

from ..utils.exceptions import SapConnectionError, SapConfigError

logger = logging.getLogger('app_sap_services')


class _SapConnectionPool:
    """线程安全的 pyrfc 连接池（每线程一个连接）"""

    def __init__(self):
        self._local = threading.local()

    def _build_config(self):
        """从 Django settings 构建 pyrfc 连接参数"""
        sap_cfg = getattr(settings, 'SAP_CONFIG', None)
        if not sap_cfg:
            raise SapConfigError(
                "未配置 SAP_CONFIG。请在 settings.py 中配置:\n"
                "SAP_CONFIG = {\n"
                "    'ashost': 'your-sap-host',\n"
                "    'sysnr': '00',\n"
                "    'client': '800',\n"
                "    'user': 'username',\n"
                "    'passwd': 'password',\n"
                "    'lang': 'ZH',\n"
                "}"
            )
        return {
            'ashost': sap_cfg['ashost'],
            'sysnr': sap_cfg.get('sysnr', '00'),
            'client': sap_cfg.get('client', '800'),
            'user': sap_cfg['user'],
            'passwd': sap_cfg['passwd'],
            'lang': sap_cfg.get('lang', 'ZH'),
        }

    def get_connection(self):
        """获取当前线程的 SAP 连接（惰性创建，首次调用时建立连接）"""
        conn = getattr(self._local, 'connection', None)
        if conn is None:
            import pyrfc
            config = self._build_config()
            try:
                conn = pyrfc.Connection(**config)
                self._local.connection = conn
                logger.info("SAP RFC 连接已建立: %s@%s sysnr=%s client=%s",
                            config['user'], config['ashost'],
                            config['sysnr'], config['client'])
            except Exception as e:
                logger.error("SAP RFC 连接失败: %s", e)
                raise SapConnectionError(f"无法连接到SAP系统: {e}") from e
        return conn

    def close(self):
        """关闭当前线程的 SAP 连接"""
        conn = getattr(self._local, 'connection', None)
        if conn is not None:
            try:
                conn.close()
                logger.info("SAP RFC 连接已关闭")
            except Exception as e:
                logger.warning("关闭SAP连接时出错: %s", e)
            finally:
                self._local.connection = None

    def health_check(self) -> bool:
        """检测 SAP 连接是否正常"""
        try:
            conn = self.get_connection()
            conn.ping()
            return True
        except Exception:
            return False


connection_pool = _SapConnectionPool()


@contextmanager
def sap_connection():
    """SAP 连接的上下文管理器，使用完毕后自动关闭"""
    try:
        conn = connection_pool.get_connection()
        yield conn
    finally:
        connection_pool.close()
