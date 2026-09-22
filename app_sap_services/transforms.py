"""SAP 原始结果集 → 可用数据 的纯转换层。

## 为什么需要这个模块

价格清洗（币种守卫、PEINH 除法顺序、KALNR 去重）与库存清洗（空工厂哨兵、
负库存、字符串补空格）原先只存在于 `sync_material_prices.py` /
`sync_material_stock.py` 两个命令的私有方法里。导出命令需要同一套口径，
若照抄一份，下次修 bug 只会改到一处 —— 报表和数据库会对同一批 SAP 数据
给出不同结果。这里把两份收敛成唯一实现。

## 两条使用路径

    写库路径   sync_material_prices / sync_material_stock
               清洗后交由 ORM 落库，价格按 price_decimals=2 舍入后入库。
    导出路径   export_material_price_stock
               清洗后直接写 Excel，用 price_decimals=None 保留原商。

## 零列空 DataFrame 的坑（本模块存在的另一半理由）

`RfcQuery._execute` 在无记录时返回的是**零列**的 `pl.DataFrame()`，不是带
schema 的空帧。零列帧上做任何列引用都会抛 ColumnNotFoundError：

    pl.DataFrame().filter(pl.col('A') > 0)       → ColumnNotFoundError
    pl.DataFrame().drop_nulls(subset=['A'])      → ColumnNotFoundError

而 `pl.concat([有列帧, 零列帧])` 会抛 ShapeError。因此：

    - 每个转换函数的第一句必须是 `if blank(df): return df`
    - 逐段收集 RFC 结果时必须跳过空帧，不能直接 concat

调用方不要依赖「记住调用顺序」，这是函数自己的责任。

## 依赖约束

本模块只依赖 polars 与标准库，**不 import Django 模型**，因此可用
SimpleTestCase 覆盖，且没有 app loading 副作用。

导出: blank, normalize_keys, clean_stock, transform_prices,
      apply_period_filter, period_ym, period_to_date, make_price_source,
      month_window, ym_label, matnr_filter_kwargs, ALLOWED_CURRENCY。
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import polars as pl

# RawMaterialPriceRecord.price 的语义是「元/基本计量单位」，模型没有币种字段，
# 非该币种记录写进去会永久污染均价口径，因此直接跳过
ALLOWED_CURRENCY = "CNY"


# ==========================================
# 通用守卫
# ==========================================

def blank(df: Optional[pl.DataFrame]) -> bool:
    """帧是否为空 —— 含「None」与「零列空帧」两种情况。

    SAP 查询无结果时 `RfcQuery` 返回零列空帧，`df.is_empty()` 为 True
    但 `df.columns == []`，此时任何列引用都会抛 ColumnNotFoundError。
    所有转换函数入口一律先用本函数挡掉。
    """
    return df is None or df.is_empty()


def normalize_keys(df: pl.DataFrame, cols) -> pl.DataFrame:
    """把指定列归一成「无前后空格的字符串」，供跨来源 join 使用。

    为什么必须做：`converters.clean_leading_zeros` 只 `lstrip('0')`，**不去
    空格**；而 `MaterialPriceQuery.IT_ITEM.BWKEY` 连 converter 都没有，库存侧
    的 `WERKS` 却是 strip 过的。主数据的 `WERKS` 只要带一个尾空格，价格和
    库存就会全部对不上，且没有任何报错 —— 全表变空是唯一症状。

    Args:
        df: 待归一化的帧（允许为空帧，原样返回）。
        cols: 需要归一的列名；帧中不存在的列自动跳过。
    """
    if blank(df):
        return df
    present = [c for c in cols if c in df.columns]
    if not present:
        return df
    return df.with_columns([
        pl.col(c).cast(pl.Utf8).fill_null("").str.strip_chars() for c in present
    ])


# ==========================================
# 库存
# ==========================================

def clean_stock(df: pl.DataFrame, warnings=None) -> pl.DataFrame:
    """库存结果集清洗。

    与写库路径逐字一致：字符串 strip、CLABS/EISBE 空值补 0、丢弃空物料号、
    **丢弃空工厂哨兵行**（SAP 零库存哨兵行工厂为空）、丢弃负库存。

    Args:
        df: ZRFC_GET_MAT_STOCK 的 IT_ITEM 帧。
        warnings: 可选 Counter；记录 `empty_plant`（被丢弃的空工厂哨兵行数）
                  供调用方复现原样的日志文本。
    """
    if blank(df):
        return df

    df = normalize_keys(df, ["MATNR", "WERKS", "LGORT", "CHARG"])
    df = df.with_columns([
        pl.col("CLABS").fill_null(0),
        pl.col("EISBE").fill_null(0),
    ])

    empty_plant = df.filter(pl.col("WERKS") == "").height
    df = df.filter(pl.col("MATNR") != "")
    df = df.filter(pl.col("WERKS") != "")
    df = df.filter(pl.col("CLABS") >= 0)

    if warnings is not None:
        warnings["empty_plant"] += empty_plant
    return df


# ==========================================
# 价格
# ==========================================

def transform_prices(
    df: pl.DataFrame,
    warnings=None,
    *,
    price_decimals: Optional[int] = 2,
) -> pl.DataFrame:
    """价格结果集清洗：单位换算 + 币种守卫 + 去重。

    Args:
        df: ZRFC_GET_MBEWH 的 IT_ITEM 帧。
        warnings: 可选 Counter；记录 `currency`（非 CNY 跳过数）与
                  `dedupe`（同期间多条成本估算去重数）。
        price_decimals: 单价保留小数位。

            - `2`（默认，写库路径）：先舍入再判 `> 0`，与历史行为一致。
            - `None`（导出路径）：**保留未舍入的原商**做 `> 0` 判断，仅由
              写出层负责显示精度。

            这个区别是有意为之。PEINH 实测取值为 1 与 10000，当 PEINH=10000
            时单价 < 0.005 的真实价格会被 `round(2)` 舍成 0 后在 `> 0` 处
            静默丢弃 —— 入库时看不出来，导成 Excel 就是个空白格。

    Returns:
        含 `UNIT_PRICE` 列的帧。除数守卫（`PEINH > 0`）在除法之前，
        顺序不可调整。
    """
    if blank(df):
        return df

    # 价格/单位字段为空（NUMC/DEC 解析失败）→ 丢弃
    df = df.drop_nulls(subset=["BDATJ", "POPER", "PEINH", "VERPR"])
    if blank(df):
        return df

    # 币种守卫：price 列语义是「元/基本计量单位」，模型没有币种字段
    currency = pl.col("WAERS").fill_null("")
    other = df.filter(currency != ALLOWED_CURRENCY)
    if other.height:
        if warnings is not None:
            warnings["currency"] += other.height
        df = df.filter(currency == ALLOWED_CURRENCY)

    # 过滤 PEINH <= 0（除零保护，必须在除法之前）
    df = df.filter(pl.col("PEINH") > 0)
    if blank(df):
        return df

    # 计算单价: VERPR / PEINH（实测只有 VERPR 有值，STPRS/PVPRS 恒为 0）
    quotient = pl.col("VERPR") / pl.col("PEINH")
    if price_decimals is not None:
        quotient = quotient.round(price_decimals)
    df = df.with_columns(quotient.alias("UNIT_PRICE"))

    # 过滤无效价格
    df = df.filter(pl.col("UNIT_PRICE") > 0)
    if blank(df):
        return df

    # ORM 的批量 upsert 不允许同一批内出现重复的幂等键（否则后端会直接报错），
    # 因此必须先去重。实测 (MATNR,BWKEY,BDATJ,POPER) 无重复，这里是防御性处理。
    # KALNR 是 NUMC12（零填充），字符串排序与数值排序等价 —— 改动此处前先确认。
    keys = ["MATNR", "BWKEY", "BDATJ", "POPER"]
    dup_count = df.height - df.select(keys).unique().height
    if dup_count:
        if warnings is not None:
            warnings["dedupe"] += dup_count
        df = df.sort(keys + ["KALNR"]).unique(subset=keys, keep="last")

    return df


def apply_period_filter(
    df: pl.DataFrame,
    ym_range,
    *,
    current_ym: int,
    include_future: bool,
    warnings=None,
) -> pl.DataFrame:
    """按 BDATJ/POPER 过滤期间。两端均形如 YYYYMM，整数比较最省事。

    Args:
        ym_range: None 表示不按区间过滤；否则闭区间 (lo, hi)。
        current_ym: 当前会计期间（YYYYMM），用于未来期间护栏。
        include_future: True 时保留未来期间。
    """
    if blank(df):
        return df

    # BDATJ/POPER 无法解析（NUMC 异常值）→ 丢弃，避免带着 None 往下走
    df = df.drop_nulls(subset=["BDATJ", "POPER"])
    if blank(df):
        return df
    ym = pl.col("BDATJ") * 100 + pl.col("POPER")

    # 未来期间护栏：price_service 取「最大日期」作为最新单价，一条未来期间的
    # 记录会静默变成当前价格并污染配方成本。SAP 会预建整年的空期间（VERPR=0，
    # 通常已被 UNIT_PRICE>0 过滤），但这里不依赖那个巧合。
    if not include_future:
        future = df.filter(ym > current_ym)
        if future.height:
            if warnings is not None:
                warnings["future"] += future.height
            df = df.filter(ym <= current_ym)

    if ym_range is None:
        return df

    lo, hi = ym_range
    return df.filter((ym >= lo) & (ym <= hi))


# ==========================================
# 会计期间
# ==========================================

def current_ym(today: Optional[date] = None) -> int:
    """当前会计期间，形如 YYYYMM。

    Args:
        today: 注入用的「今天」；默认取宿主本地日期。
               调用方要按项目时区取日期时应显式传入
               `timezone.localdate()`。
    """
    today = today or date.today()
    return today.year * 100 + today.month


def period_ym(bdatj, poper) -> Optional[int]:
    """会计年度 + 会计期间 → YYYYMM。

    纯算术，与 `apply_period_filter` 内 Polars 端的
    `BDATJ * 100 + POPER` 等价。不做期间合法性校验 —— POPER 为 0 或 13
    （调整期间）会得到 YYYY00 / YYYY13，这类值永远匹配不上月份窗口，
    由调用方按需计数。
    """
    if bdatj is None or poper is None:
        return None
    try:
        return int(bdatj) * 100 + int(poper)
    except (ValueError, TypeError):
        return None


def period_to_date(bdatj, poper) -> Optional[date]:
    """会计年度 + 会计期间 → 该期间首日。

    Returns:
        date(2026, 9, 1)；任一值缺失或非法（如 POPER=13）时返回 None
    """
    if not bdatj or not poper:
        return None
    try:
        return date(int(bdatj), int(poper), 1)
    except (ValueError, TypeError):
        return None


def make_price_source(bdatj: int, poper: int, bwkey: str = "") -> str:
    """生成价格来源标识，如 'SAP MBEWH 2026-01 [3011]'。

    从 MBEW 改为 MBEWH 是有意为之 —— 新旧两代 RFC 写出的来源必须可区分。
    """
    base = f"SAP MBEWH {bdatj}-{poper:02d}"
    return f"{base} [{bwkey}]" if bwkey else base


# ==========================================
# 月份窗口
# ==========================================

def month_window(end_ym: int, n: int) -> list:
    """最近 n 个月（含 end_ym 本身），升序 YYYYMM 列表。

    >>> month_window(202603, 12)[0]
    202503
    >>> month_window(202603, 1)
    [202603]
    """
    if n < 1:
        raise ValueError("n 必须 >= 1")
    year, month = divmod(end_ym, 100)
    start = year * 12 + (month - 1) - (n - 1)
    return [(start + i) // 12 * 100 + (start + i) % 12 + 1 for i in range(n)]


def ym_label(ym: int) -> str:
    """202510 → '2025-10'"""
    return f"{ym // 100:04d}-{ym % 100:02d}"


# ==========================================
# SAP range 参数
# ==========================================

def matnr_filter_kwargs(matnr: str) -> dict:
    """SAP Range：无通配用 EQ（才能拿到零库存哨兵行），有 * 用 CP。"""
    if not matnr:
        return {}
    if "*" in matnr:
        return {"mat_range__cp": matnr}
    return {"mat_range__eq": matnr}
