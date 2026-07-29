"""
SAPGateway — SAP 服务模块顶层入口。

管理 ConnectionManager 并提供 RFC 调用的统一入口：
- sap.rfc(SchemaClass) → RfcQuery 链式 builder
- sap.call(SchemaClass, **kwargs) → 快捷一步调用

使用示例:
    from app_sap_services import sap
    from app_sap_services.definitions.material import MaterialQuery

    # 链式调用
    result = sap.rfc(MaterialQuery).filter(mat_range__cp="A01*").call()

    # 快捷调用
    result = sap.call(MaterialQuery, mat_range__cp="A01*")
"""

import logging
import threading
from typing import Dict, List, Optional, Type, Any

from ..config import SAPConfig
from ..connection import ConnectionManager
from ..exceptions import SAPRfcError

logger = logging.getLogger("sap.gateway")


class SAPGateway:
    """
    SAP RFC 服务网关。

    持有全局 ConnectionManager，提供 RFC 调用的统一入口。
    """

    def __init__(self, conn_mgr: ConnectionManager):
        self._conn_mgr = conn_mgr

    # =========================================================================
    # 主要 API
    # =========================================================================

    def rfc(self, schema_class: Type["RfcSchema"]) -> "RfcQuery":
        """
        创建 RFC 链式查询 builder。

        Args:
            schema_class: RfcSchema 子类（RFC 函数定义）

        Returns:
            RfcQuery 实例，可链式 .filter().limit().call()

        Example:
            from app_sap_services.definitions.material import MaterialQuery

            result = sap.rfc(MaterialQuery) \
                .filter(mat_range__cp="A01*") \
                .filter(mta_range__eq="ROH") \
                .limit(50) \
                .call()
        """
        from .builder import RfcQuery

        return RfcQuery(schema_class, self._conn_mgr)

    def call(self, schema_class: Type["RfcSchema"], **kwargs) -> List:
        """
        快捷调用：一次 RFC 调用，无需链式 .filter()。

        Args:
            schema_class: RfcSchema 子类
            **kwargs: 筛选条件，格式为 param__op=value
                      如 mat_range__cp="A01*", mta_range__eq="ROH"

        Returns:
            类型化的 OutputRecord 列表（如果有输出表），否则为原始 dict

        Example:
            result = sap.call(MaterialQuery, mat_range__cp="A01*", mta_range__eq="ROH")
            for row in result:
                print(row.MATNR)
        """
        return self.rfc(schema_class).filter(**kwargs).call()

    # =========================================================================
    # 连接管理
    # =========================================================================

    def health_check(self) -> dict:
        """SAP 连接健康检查"""
        try:
            return self._conn_mgr.health_check()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close(self):
        """关闭当前线程的 SAP 连接（用于应用关闭时清理资源）"""
        self._conn_mgr.close()

    def execute_raw(
        self,
        function_name: str,
        **params,
    ) -> Dict[str, Any]:
        """
        原始 RFC 调用（用于未声明 Schema 的临时调用或调试）。

        Args:
            function_name: RFC 函数名
            **params: pyrfc 调用参数

        Returns:
            SAP 返回的原始字典
        """
        conn = None
        try:
            conn = self._conn_mgr.get_connection()
            logger.debug(f"RFC 调用: {function_name}, params: {list(params.keys())}")
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
                self._conn_mgr.release_connection(conn)


# =============================================================================
# 模块级惰性单例（线程安全双检锁）
# =============================================================================

_gateway: Optional[SAPGateway] = None
_gateway_lock = threading.Lock()


def _get_gateway() -> SAPGateway:
    """获取全局 SAPGateway 单例（线程安全惰性初始化）"""
    global _gateway
    if _gateway is None:
        with _gateway_lock:
            if _gateway is None:
                config = SAPConfig.from_django_settings()
                conn_mgr = ConnectionManager(config)
                _gateway = SAPGateway(conn_mgr)
    return _gateway
