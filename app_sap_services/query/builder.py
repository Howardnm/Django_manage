"""
RfcQuery — RFC 链式查询构建器（Polars 引擎驱动）。

SAP 负责数据来源（RFC 调用），Polars 负责所有客户端数据处理。
OutputRecord 只在 .call() 返回时按需生成。

链式调用:
    sap.rfc(MaterialQuery)                       # → RfcQuery
       .filter(mta_range__eq="ROH")              # SAP 服务端筛选
       .exclude(mat_range__cp="Z*")              # SAP 服务端排除
       .order_by("MATNR")                        # Polars sort
       .offset(20).limit(10)                     # Polars slice
       .select("MATNR", "MAKTX")                 # Polars select
       .call()                                   # → List[OutputRecord]
       .collect()                                # → pl.DataFrame（跳过转换）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple, TYPE_CHECKING

import polars as pl

from ..exceptions import SAPFilterError, DoesNotExist, MultipleObjectsReturned

if TYPE_CHECKING:
    from ..schemas.base import RfcSchema
    from ..connection import ConnectionManager

logger = logging.getLogger("sap.query")

# ---------------------------------------------------------------------------
# having 条件 → Polars filter 的 dispatch 表
# ---------------------------------------------------------------------------

def _having_eq(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    return df.filter(pl.col(col) == value)

def _having_ne(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    return df.filter(pl.col(col) != value)

def _having_gt(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    return df.filter(pl.col(col) > value)

def _having_ge(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    return df.filter(pl.col(col) >= value)

def _having_lt(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    return df.filter(pl.col(col) < value)

def _having_le(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    return df.filter(pl.col(col) <= value)

def _having_bt(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return df.filter((pl.col(col) >= value[0]) & (pl.col(col) <= value[1]))
    return df

def _having_cp(df: pl.DataFrame, col: str, value: Any) -> pl.DataFrame:
    pattern = str(value).replace("*", ".*")
    return df.filter(pl.col(col).cast(pl.Utf8).str.contains(pattern))

HAVING_OPS: Dict[str, Any] = {
    "EQ": _having_eq, "NE": _having_ne,
    "GT": _having_gt, "GE": _having_ge,
    "LT": _having_lt, "LE": _having_le,
    "BT": _having_bt, "CP": _having_cp,
}


class RfcQuery:
    """
    RFC 链式查询构建器（可变 Builder + 返回 self，Polars 引擎驱动）。

        sap.rfc(MaterialQuery)
           .filter(mta_range__eq="ROH")
           .order_by("MATNR").offset(20).limit(10)
           .call()      # → List[OutputRecord]
           .collect()   # → pl.DataFrame
    """

    __slots__ = (
        "_schema", "_conn_mgr",
        "_filters", "_excludes",
        "_limit", "_offset", "_select_fields", "_order_by",
        "_group_by", "_having",
        "_aggregated", "_empty", "_df",
    )

    def __init__(
        self,
        schema_class: type[RfcSchema],
        conn_mgr: ConnectionManager,
    ):
        self._schema = schema_class
        self._conn_mgr = conn_mgr
        self._filters: Dict[str, Any] = {}
        self._excludes: Dict[str, Any] = {}
        self._limit: Optional[int] = None
        self._offset: int = 0
        self._select_fields: Optional[List[str]] = None
        self._order_by: List[Tuple[str, bool]] = []
        self._group_by: List[str] = []
        self._having: Dict[str, Any] = {}
        self._aggregated: Optional[List[Dict[str, Any]]] = None
        self._empty: bool = False
        self._df: Optional[pl.DataFrame] = None

    # =========================================================================
    # 链式 — 筛选（SAP 服务端）
    # =========================================================================

    def filter(self, **kwargs) -> RfcQuery:
        """添加 SAP Range Table 筛选条件。"""
        self._filters.update(kwargs)
        return self

    def exclude(self, **kwargs) -> RfcQuery:
        """添加排除条件 SIGN="E"（SAP 服务端）。"""
        self._excludes.update(kwargs)
        return self

    # =========================================================================
    # 链式 — 排序 / 分页 / 投影（Polars 引擎延迟执行）
    # =========================================================================

    def order_by(self, *fields: str) -> RfcQuery:
        """客户端排序。字段前加 '-' 降序。"""
        valid_fields: set = set()
        for ot in self._schema._output_tables.values():
            valid_fields.update(ot._fields.keys())
        parsed = []
        for f in fields:
            f = f.strip()
            field_name = f[1:] if f.startswith("-") else f
            if valid_fields and field_name not in valid_fields:
                logger.warning(f"order_by() 字段 {field_name!r} 不在输出表中")
            parsed.append((f[1:], True) if f.startswith("-") else (f, False))
        self._order_by = parsed
        return self

    def limit(self, n: Optional[int]) -> RfcQuery:
        self._limit = n
        return self

    def offset(self, n: int) -> RfcQuery:
        self._offset = max(0, n)
        return self

    def select(self, *field_names: str) -> RfcQuery:
        self._select_fields = list(field_names) if field_names else None
        return self

    # =========================================================================
    # 链式 — 分组
    # =========================================================================

    def group_by(self, *fields: str) -> RfcQuery:
        self._group_by = list(fields)
        return self

    def having(self, **conditions) -> RfcQuery:
        self._having.update(conditions)
        return self

    def agg(self, **aggs) -> RfcQuery:
        """分组聚合（Polars group_by + agg）。"""
        if not self._group_by:
            logger.warning("agg() 未配合 group_by() 使用，将返回空列表。")
        self._execute()
        self._do_aggregate(**aggs)
        return self

    # =========================================================================
    # 终端
    # =========================================================================

    def call(self) -> List:
        """执行 RFC 调用，返回结果。

        Returns:
            - 常规:    List[OutputRecord]
            - 分组:    Dict[Tuple, List[OutputRecord]]
            - 已 agg:  List[Dict]（应用 having）
        """
        if self._aggregated is not None:
            return self._apply_having(self._aggregated)
        self._execute()
        if self._group_by:
            return self._to_grouped_dict()
        return self._df_to_records()

    def collect(self) -> pl.DataFrame:
        """终端：返回 Polars DataFrame（跳过 OutputRecord 转换）。"""
        if self._aggregated is not None:
            results = self._apply_having(self._aggregated)
            return pl.DataFrame(results) if results else pl.DataFrame()
        self._execute()
        return self._df.clone() if self._df is not None else pl.DataFrame()

    def to_polars(self) -> pl.DataFrame:
        return self.collect()

    # =========================================================================
    # 便捷终端 — 全部基于 Polars DataFrame，不绕路 OutputRecord
    # =========================================================================

    def first(self):
        """返回第一条记录。无结果返回 None。"""
        clone = self.clone()
        clone._limit = 1
        clone._execute()
        if clone._df is None or clone._df.is_empty():
            return None
        return _df_first_row(clone._df, clone._record_cls)

    def last(self):
        """返回最后一条记录。无结果返回 None。"""
        self._execute()
        if self._df is None or self._df.is_empty():
            return None
        return _df_first_row(self._df.tail(1), self._record_cls)

    def get(self, **kwargs):
        """返回唯一匹配记录。0 条 → DoesNotExist，>1 条 → MultipleObjectsReturned。"""
        if kwargs:
            self._filters.update(kwargs)
        self._execute()
        if self._df is None or self._df.is_empty():
            raise DoesNotExist(
                f"[{self._schema.function_name}] 未找到匹配记录: {kwargs}"
            )
        if self._df.height > 1:
            raise MultipleObjectsReturned(
                f"[{self._schema.function_name}] 找到 {self._df.height} 条匹配记录: {kwargs}"
            )
        return _df_first_row(self._df, self._record_cls)

    def exists(self) -> bool:
        clone = self.clone()
        clone._limit = 1
        clone._execute()
        return clone._df is not None and not clone._df.is_empty()

    def count(self) -> int:
        """返回行数。已执行查询时 O(1)。"""
        if self._aggregated is not None:
            return len(self._aggregated)
        if self._df is not None:
            return self._df.height
        self._execute()
        return self._df.height if self._df is not None else 0

    def all(self) -> List:
        return self.call()

    # =========================================================================
    # 数据导出 — 直接用 Polars API，完全不触 OutputRecord
    # =========================================================================

    def values(self, *fields: str) -> List[Dict[str, Any]]:
        """返回 dict 列表（Polars to_dicts）。"""
        self._execute()
        if self._df is None or self._df.is_empty():
            return []
        cols = list(fields) if fields else list(self._df.columns)
        available = [c for c in cols if c in self._df.columns]
        return self._df.select(available).to_dicts() if available else []

    def values_list(self, *fields: str, flat: bool = False) -> List:
        """返回元组列表 / 扁平列表。"""
        self._execute()
        if self._df is None or self._df.is_empty():
            return []
        cols = list(fields)
        available = [c for c in cols if c in self._df.columns]
        if not available:
            return []
        if flat and len(cols) == 1:
            return self._df.get_column(available[0]).to_list()
        return list(self._df.select(available).rows())

    # =========================================================================
    # 迭代器
    # =========================================================================

    def iterator(self, chunk_size: int = 1000) -> Iterator[List]:
        """分批迭代。"""
        if chunk_size <= 0:
            raise ValueError(f"iterator() chunk_size 必须 > 0")
        self._execute()
        if self._df is None or self._df.is_empty():
            return
        rec_cls = self._record_cls
        for s in self._df.iter_slices(chunk_size):
            yield [rec_cls(row) for row in s.to_dicts()]

    # =========================================================================
    # 实例管理
    # =========================================================================

    def clone(self) -> RfcQuery:
        """独立副本。"""
        new = RfcQuery(self._schema, self._conn_mgr)
        new._filters = dict(self._filters)
        new._excludes = dict(self._excludes)
        new._limit = self._limit
        new._offset = self._offset
        new._select_fields = list(self._select_fields) if self._select_fields else None
        new._order_by = list(self._order_by)
        new._group_by = list(self._group_by)
        new._having = dict(self._having)
        new._empty = self._empty
        return new

    def none(self) -> RfcQuery:
        self._empty = True
        return self

    # =========================================================================
    # 调试
    # =========================================================================

    def explain(self) -> str:
        lines = [f"RfcQuery({self._schema.function_name})"]
        if self._empty:
            lines.append("  [EMPTY]")
            return "\n".join(lines)
        lines.append(f"  Filters: {self._filters}")
        if self._excludes:
            lines.append(f"  Excludes: {self._excludes}")
        try:
            p = self._schema.build_params(**{**self._filters, **self._excludes})
            lines.append(f"  Params: {list(p.keys())}")
        except Exception as e:
            lines.append(f"  [参数构建失败: {e}]")
        for label, val in [
            ("Order by", self._order_by), ("Limit", self._limit),
            ("Offset", self._offset), ("Select", self._select_fields),
            ("Group by", self._group_by), ("Having", self._having),
        ]:
            if val:
                lines.append(f"  {label}: {val}")
        return "\n".join(lines)

    def show(self, n: int = 20, *fields: str) -> None:
        clone = self.clone()
        clone._limit = n
        clone._execute()
        if clone._df is None or clone._df.is_empty():
            print("(empty)")
            return
        df = clone._df
        if fields:
            available = [f for f in fields if f in df.columns]
            df = df.select(available) if available else df
        print(df)

    def __repr__(self):
        p = [f"RfcQuery({self._schema.function_name}"]
        if self._empty:       p.append(", EMPTY")
        if self._filters:     p.append(f", f={len(self._filters)}")
        if self._excludes:    p.append(f", x={len(self._excludes)}")
        if self._order_by:    p.append(f", sort={len(self._order_by)}")
        if self._group_by:    p.append(f", gb={len(self._group_by)}")
        p.append(")")
        return "".join(p)

    # =========================================================================
    # 内部 — 查询执行管道
    # =========================================================================

    @property
    def _record_cls(self):
        """OutputRecord 工厂类（懒加载 + 缓存）。"""
        first = list(self._schema._output_tables.keys())[0]
        return self._schema._output_tables[first]._get_record_cls()

    # ------------------------------------------------------------------
    # 核心执行
    # ------------------------------------------------------------------

    def _execute(self):
        """SAP 查询 → Polars DataFrame → 应用 transforms"""
        if self._empty:
            self._df = pl.DataFrame()
            return
        # 1. 构建 SAP 参数
        params = self._build_params()
        # 2. SAP RFC 调用
        raw = self._conn_mgr.call_rfc(self._schema.function_name, **params)
        # 3. 解析 → 提取输出表 → Polars DataFrame
        parsed = self._schema.parse_response(raw)
        if self._schema._output_tables:
            first = list(self._schema._output_tables.keys())[0]
            records = parsed.get(first, [])
        else:
            records = parsed
        self._df = (
            pl.DataFrame([r._data for r in records])
            if isinstance(records, list) and records
            else pl.DataFrame()
        )
        # 4. Polars transforms
        self._apply_transforms()

    def _build_params(self) -> Dict[str, Any]:
        """构建 SAP pyrfc 参数（含 filter + exclude SIGN="E"）。"""
        all_f = dict(self._filters)
        for k, v in self._excludes.items():
            all_f[k] = v
        try:
            params = self._schema.build_params(**all_f)
        except ValueError as e:
            raise SAPFilterError(f"[{self._schema.function_name}] 参数构建失败: {e}") from e
        # exclude → SIGN="E"
        for key in self._excludes:
            attr = key.split("__")[0]
            if attr not in self._schema._range_params:
                raise SAPFilterError(
                    f"exclude() 未知参数 {attr!r}，可用: "
                    f"{list(self._schema._range_params.keys())}"
                )
            pname = self._schema._range_params[attr].rfc_name
            if pname in params:
                for row in params[pname]:
                    if row.get("SIGN") == "I":
                        row["SIGN"] = "E"
        return params

    def _apply_transforms(self):
        """在 Polars DataFrame 上执行 select / sort / slice"""
        df = self._df
        if df is None or df.is_empty():
            return
        # select
        if self._select_fields:
            avail = [c for c in self._select_fields if c in df.columns]
            if avail:
                df = df.select(avail)
            missing = set(self._select_fields) - set(avail)
            if missing:
                logger.warning(f"select() 字段不存在: {missing}")
        # sort
        if self._order_by:
            by, desc = [], []
            for f, r in self._order_by:
                if f in df.columns:
                    by.append(f); desc.append(r)
            if by:
                df = df.sort(by, descending=desc, nulls_last=True)
        # slice
        if self._offset > 0 or self._limit is not None:
            start = self._offset
            length = self._limit if self._limit is not None else max(0, df.height - start)
            df = df.slice(start, length)
        self._df = df

    # ------------------------------------------------------------------
    # 聚合
    # ------------------------------------------------------------------

    def _do_aggregate(self, **aggs):
        df = self._df
        if df is None or df.is_empty() or not self._group_by:
            self._aggregated = []; return
        gcols = [g for g in self._group_by if g in df.columns]
        if not gcols:
            self._aggregated = []; return
        exprs = []
        if "count" in aggs:
            label = aggs["count"] if isinstance(aggs["count"], str) else "count"
            exprs.append(pl.count().alias(label))
        agg_map = {"sum": pl.sum, "avg": pl.mean, "min": pl.min, "max": pl.max}
        for atype, fn in agg_map.items():
            fields = aggs.get(atype, [])
            if isinstance(fields, str):
                fields = [fields] if fields else []
            for f in fields:
                if f in df.columns:
                    exprs.append(fn(f).alias(f"{atype}_{f}"))
        if exprs:
            self._aggregated = df.group_by(gcols).agg(exprs).sort(gcols).to_dicts()
        else:
            self._aggregated = []

    def _apply_having(self, results: List[Dict]) -> List[Dict]:
        if results is None or not results or not self._having:
            return results or []
        from ..schemas.params import OP_SUFFIX_MAP
        df = pl.DataFrame(results)
        for key, value in self._having.items():
            for suffix, sap_op in OP_SUFFIX_MAP.items():
                if key.endswith(suffix):
                    col = key[:-len(suffix)]
                    if col in df.columns:
                        fn = HAVING_OPS.get(sap_op)
                        if fn:
                            df = fn(df, col, value)
                    break
        return df.to_dicts()

    # ------------------------------------------------------------------
    # DataFrame → OutputRecord 转换
    # ------------------------------------------------------------------

    def _df_to_records(self) -> List:
        if self._df is None or self._df.is_empty():
            return []
        rec = self._record_cls
        return [rec(row) for row in self._df.to_dicts()]

    def _to_grouped_dict(self) -> Dict[Tuple, List]:
        if self._df is None or self._df.is_empty():
            return {}
        rec = self._record_cls
        parts = self._df.partition_by(self._group_by, as_dict=True)
        return {
            k: [rec(row) for row in df.to_dicts()]
            for k, df in parts.items()
        }


# =============================================================================
# 模块级辅助函数
# =============================================================================

def _df_first_row(df: pl.DataFrame, record_cls: type) -> Any:
    """DataFrame 第一行 → OutputRecord。"""
    rows = df.to_dicts()
    return record_cls(rows[0]) if rows else None
