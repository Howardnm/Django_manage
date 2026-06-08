"""
SAP RFC 服务基类 —— 可扩展性核心。

所有域服务继承此类，获得统一的 RFC 调用、过滤条件构建、结果解析能力。
子类只需为每个 RFC 函数定义一个方法，遵循三步模式:
  1. 构建筛选条件 (build_range / SAPFilter)
  2. 调用 RFC (_call_rfc)
  3. 解析结果 (parse_result)
"""

import logging
from typing import Dict, List, Optional, Any

from .connection import ConnectionManager
from .exceptions import SAPRfcError, SAPConnectionError

logger = logging.getLogger('sap.service')


class BaseSAPService:
    """
    SAP RFC 服务基类。

    子类可覆盖 FIELD_NAME_MAP 来指定该域中共用的字段名映射。
    """

    # 字段名 → (Low键名, High键名) 映射
    # 标准 SAP range table 使用 LOW/HIGH，但部分表使用自定义字段名
    # 如 MTART 对应 {'MTART_LOW': '', 'MTART_HIGH': ''}
    FIELD_NAME_MAP: Dict[str, tuple] = {}

    def __init__(self, connection_manager: ConnectionManager):
        self._conn_mgr = connection_manager

    # ==================================================================
    # 核心 RFC 调用
    # ==================================================================

    def _call_rfc(
        self,
        function_name: str,
        **params,
    ) -> Dict[str, Any]:
        """
        统一 RFC 调用入口。

        自动处理: 获取连接 → 调用 RFC → 错误包装 → 归还连接。
        调用方无需关心连接生命周期。

        Args:
            function_name: RFC 函数名，如 'ZRFC_MATERIAL_MESN'
            **params: 传递给 RFC 的参数（import params 和 table params）

        Returns:
            RFC 返回的原始字典

        Raises:
            SAPRfcError: RFC 调用返回错误时
            SAPConnectionError: 连接失败时
        """
        conn = None
        try:
            conn = self._conn_mgr.get_connection()
            logger.debug(f"RFC 调用: {function_name}, params: {list(params.keys())}")
            result = conn.call(function_name, **params)
            logger.info(
                f"RFC 调用成功: {function_name}, "
                f"返回表: {[k for k in result.keys() if isinstance(result[k], list)]}"
            )
            return result
        except SAPRfcError:
            raise
        except Exception as e:
            # pyrfc 的 RFCError 可能在此处被捕获
            raise SAPRfcError(
                function=function_name,
                message=str(e),
                params={k: str(v)[:200] for k, v in params.items()},
            ) from e
        finally:
            if conn:
                self._conn_mgr.release_connection(conn)

    # ==================================================================
    # 过滤条件构建
    # ==================================================================

    def build_range(
        self,
        sign: str = 'I',
        option: str = 'EQ',
        low: str = '',
        high: str = '',
        **extra_fields,
    ) -> Dict[str, str]:
        """
        构建单个 SAP Range Table 行。

        Args:
            sign:   'I' = 包含(Include), 'E' = 排除(Exclude)
            option: 'EQ' = 等于, 'BT' = 介于, 'CP' = 包含模式(支持通配符 *)
                    'NE' = 不等于, 'GT' = 大于, 'LT' = 小于
                    'GE' = 大于等于, 'LE' = 小于等于, 'NB' = 不介于
            low:    下限值/单个值。CP 模式下 * 匹配任意字符 (如 'A01*')
            high:   上限值（仅 BT/NB 模式使用）
            **extra_fields: 当 SAP 表使用非标准字段名时传入
                           如 MTART_LOW='ROH', MTART_HIGH=''

        Returns:
            dict: 可直接放入 range table 列表的字典

        Example:
            # 标准字段名 (LOW/HIGH)
            self.build_range('I', 'CP', 'A01001*')

            # 自定义字段名 (MTART_LOW/MTART_HIGH)
            self.build_range('I', 'EQ', MTART_LOW='ROH', MTART_HIGH='')
        """
        row = {'SIGN': sign, 'OPTION': option}
        if extra_fields:
            row.update(extra_fields)
        else:
            row['LOW'] = low
            row['HIGH'] = high
        return row

    def build_range_table(
        self,
        entries: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        批量构建 Range Table（别名，语义更清晰）。
        等价于直接传入 entries 列表。
        """
        return entries

    # ==================================================================
    # 结果解析
    # ==================================================================

    def parse_result(
        self,
        result: Dict[str, Any],
        table_key: str,
        field_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        从 RFC 返回结果中提取指定表并做字段映射。

        Args:
            result:    _call_rfc() 返回的原始字典
            table_key: 目标表名，如 'ZMARC', 'IT_OUTPUT', 'TB_KNA1'
            field_map: 可选，{SAP字段名: Python字段名} 映射

        Returns:
            list[dict]: 记录列表，字段名已按 field_map 重命名
        """
        records = result.get(table_key, [])
        if not isinstance(records, list):
            logger.warning(f"表 {table_key} 返回非列表类型: {type(records)}")
            return []

        if field_map:
            records = [
                {field_map.get(k, k): v for k, v in r.items()}
                for r in records
            ]

        logger.info(f"解析表 {table_key}: {len(records)} 条记录")
        return records

    # ==================================================================
    # 工具方法
    # ==================================================================

    @staticmethod
    def clean_material_no(matnr: Optional[str]) -> str:
        """清理物料编号前导零"""
        if not matnr:
            return ''
        return matnr.lstrip('0') or matnr

    @staticmethod
    def clean_leading_zeros(value: Optional[str]) -> str:
        """通用去前导零"""
        if not value:
            return ''
        return value.lstrip('0') or value
