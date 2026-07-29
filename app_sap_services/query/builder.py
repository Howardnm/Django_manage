"""
RfcQuery — RFC 链式查询构建器（pandas/spark 风格 API）。

通过 sap.rfc(SchemaClass) 创建，支持链式调用：
    .filter(param__op=value)  — 添加 Range Table 筛选条件
    .limit(n)                 — 限制返回行数
    .call()                   — 执行 RFC 调用，返回类型化结果

设计理念:
    - 每次 .filter() 添加条件，不修改之前的条件
    - .call() 是终端操作，触发实际 SAP 调用
    - 结果自动通过 Schema 的 OutputTable 进行类型转换
"""

import logging
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from ..exceptions import SAPRfcError, SAPFilterError

if TYPE_CHECKING:
    from ..schemas.base import RfcSchema
    from ..connection import ConnectionManager

logger = logging.getLogger("sap.query")


class RfcQuery:
    """
    RFC 链式查询构建器。

    不可变风格：每个 .filter() 返回新实例，但为了性能采用内部可变 + 返回 self。
    """

    def __init__(
        self,
        schema_class: "Type[RfcSchema]",
        conn_mgr: "ConnectionManager",
    ):
        self._schema = schema_class
        self._conn_mgr = conn_mgr
        self._filters: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._select_fields: Optional[List[str]] = None

    # =========================================================================
    # 链式方法
    # =========================================================================

    def filter(self, **kwargs) -> "RfcQuery":
        """
        添加 Range Table / Import / Table 筛选条件。

        支持 param__op=value 格式：
            param__eq, param__ne, param__cp, param__np,
            param__bt, param__nb, param__gt, param__lt,
            param__ge, param__le

        也支持直接传 Import 参数名：
            iv_matnr="A01001"

        Example:
            query.filter(mat_range__cp="A01*")
                 .filter(mta_range__eq="ROH")
                 .filter(wek_range__eq="1010")
        """
        self._filters.update(kwargs)
        return self

    def limit(self, n: Optional[int]) -> "RfcQuery":
        """限制返回行数（客户端切片）。传 None 取消限制。"""
        self._limit = n
        return self

    def select(self, *field_names: str) -> "RfcQuery":
        """
        字段投影：只返回指定字段。

        Args:
            *field_names: 要保留的字段名（SAP 原始字段名）

        Note:
            投影在类型转换后执行，不影响 SAP 端查询。
        """
        self._select_fields = list(field_names) if field_names else None
        return self

    # =========================================================================
    # 终端操作
    # =========================================================================

    def call(self) -> List:
        """
        执行 RFC 调用并返回结果。

        Returns:
            - 如果有输出表：返回 OutputRecord 列表
            - 如果没有输出表：返回原始 dict

        Raises:
            SAPRfcError: RFC 调用失败时
        """
        # 1. 构建 pyrfc 参数字典
        try:
            params = self._schema.build_params(**self._filters)
        except ValueError as e:
            raise SAPFilterError(
                f"[{self._schema.function_name}] 参数构建失败: {e}"
            ) from e

        # 2. 调用 RFC
        conn = None
        try:
            conn = self._conn_mgr.get_connection()
            logger.debug(
                f"RFC 调用: {self._schema.function_name}, "
                f"params: {list(params.keys())}"
            )
            raw_response = conn.call(self._schema.function_name, **params)
            logger.info(f"RFC 调用成功: {self._schema.function_name}")
        except SAPRfcError:
            raise
        except Exception as e:
            raise SAPRfcError(
                function=self._schema.function_name,
                message=str(e),
                params={k: str(v)[:200] for k, v in params.items()},
            ) from e
        finally:
            if conn:
                self._conn_mgr.release_connection(conn)

        # 3. 解析响应
        parsed = self._schema.parse_response(raw_response)

        # 4. 提取输出表
        if self._schema._output_tables:
            result = list(parsed.values())[0]
        else:
            result = parsed

        # 5. 字段投影（类型转换后对 OutputRecord._data 做字段过滤）
        if self._select_fields and isinstance(result, list):
            result = [
                type(r)({k: r._data[k] for k in self._select_fields if k in r._data})
                for r in result
                if hasattr(r, "_data")
            ] or result  # 如果列表中没有任何 OutputRecord，回退到原结果

        # 6. 行数限制
        if self._limit is not None and isinstance(result, list):
            result = result[: self._limit]

        return result

    def first(self):
        """
        返回第一条结果。

        如果没有结果返回 None。

        NOTE: 此方法不会修改 builder 的 limit 设置，
              调用后可继续使用原 builder。
        """
        original_limit = self._limit
        self._limit = 1
        try:
            results = self.call()
            return results[0] if results else None
        finally:
            self._limit = original_limit

    def count(self) -> int:
        """
        执行调用并返回结果行数。

        NOTE: SAP RFC 不支持服务端 COUNT，此方法会拉取全部数据后取 len()。
              对大数据集请使用 .call() 后自行 len(result) 避免重复调用。
        """
        results = self.call()
        if isinstance(results, list):
            return len(results)
        return 0

    # =========================================================================
    # 调试
    # =========================================================================

    def explain(self) -> str:
        """输出当前查询计划（调试用）"""
        lines = [
            f"RfcQuery({self._schema.function_name})",
            f"  Filters: {self._filters}",
        ]
        try:
            params = self._schema.build_params(**self._filters)
            lines.append(f"  Pyrfc params: {list(params.keys())}")
            for k, v in params.items():
                if isinstance(v, list):
                    lines.append(f"    {k}: {len(v)} 行")
        except Exception as e:
            lines.append(f"  [参数构建失败: {e}]")

        if self._limit is not None:
            lines.append(f"  Limit: {self._limit}")
        if self._select_fields:
            lines.append(f"  Select: {self._select_fields}")

        return "\n".join(lines)

    def __repr__(self):
        return f"RfcQuery({self._schema.function_name}, filters={len(self._filters)})"
