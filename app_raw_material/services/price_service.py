"""原材料价格计算服务 — 全项目唯一的「价格聚合 + 批量装载」实现。

## 为什么需要这个模块

价格有两条消费路径，历史上各自实现了一套聚合：

    单条路径   RawMaterial.latest_price / avg_price / *_for_plant
               每个属性各打 2~3 条聚合查询，在多配方页面上退化为 N+1。
    批量路径   common_utils/serializers/compare.py 的 _compute_price_maps
               一次取回全部记录，Python 侧聚合。

两者语义必须逐字一致却靠人工同步，已经出现分叉（见「口径统一」一节）。
本模块把两条路径收敛到同一个内核：单条 property 与批量查表都走
`latest_from_series` / `avg_from_series`，只是装载方式不同。

## 三个口径（全项目唯一定义）

    最新单价 latest = 全库最大日期上、该日期全部报价的平均值
    近N月均价 avg   = 近 N 月窗口内「先按日均值、再对日均值求平均」
    窗口为空时 avg 回落 latest

注意 avg 不是「窗口内所有记录的平均」—— 是「日均值的均值」（mean of means）。
这个区别在「同一天有多条报价、不同天记录条数不等」时会让结果不同，
`avg_from_series` 的 docstring 与单测里各有一处判别性说明。

## 价格不落库

价格全部从 `RawMaterialPriceRecord` 实时算出，原材料表上没有任何价格缓存列。
（历史上曾有 `_latest_price` / `_avg_price` 两个反规范化列，需要靠
RawMaterial 的 pre/post_save 信号级联维护配方成本；因为「直接写价格记录」
不会触发那条信号，缓存值与实时值长期不自洽，已连同级联信号一并删除。）

## 口径统一（相对旧实现的行为变更）

    latest_price_for_plant   旧：order_by('-date').first() 取单条记录
                             新：该工厂当日跨供应商均价（与全局口径同算法）
    avg_price_for_plant      旧：窗口内直接 Avg（记录级均值）
                             新：窗口内日均值再平均（与全局口径同算法）

## 循环 import 约束

本模块顶层 import models；`app_raw_material/models.py` 只在**函数体内**延迟
import 本模块。反向的顶层 import 会成环，勿改。

导出: RawMaterialPriceLookup, RawMaterialPriceService, latest_from_series,
      avg_from_series。
"""

import logging
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg

from app_raw_material.models import PriceAvgConfig, RawMaterialPriceRecord

logger = logging.getLogger(__name__)

# 聚合结果的量化精度 —— 与 DecimalField(max_digits=10, decimal_places=2) 对齐
_PRECISION = Decimal('0.01')

# series() 缓存中「全局维度」的键（工厂维度用 plant_id，二者不会冲突）
_GLOBAL = '__global__'

# 价格窗口的天数换算 —— 与 PriceAvgConfig.months 配合，保持历史行为不变
_DAYS_PER_MONTH = 30


def _plant_key(plant):
    """把 None / Plant 实例 / plant_id 归一化成 series() 的缓存键。

    Returns:
        (cache_key, plant_id) — 全局维度为 (_GLOBAL, None)
    """
    if plant is None:
        return _GLOBAL, None
    plant_id = plant if isinstance(plant, int) else plant.pk
    return plant_id, plant_id


def _rm_id(material):
    """把 RawMaterial 实例或裸 id 归一化成 rm_id。"""
    return material if isinstance(material, int) else material.pk


# ==========================================
# 纯算术内核（无 ORM 依赖，可 SimpleTestCase 覆盖）
# ==========================================

def latest_from_series(series):
    """从日均序列取「最新单价」。

    Args:
        series: [(date, day_avg), ...]，按 date 升序、同 date 已合并。
    Returns:
        Decimal（量化到 0.01）或 None（序列为空）。

    契约：None 表示「无数据」。Decimal('0.00') 是有效价格，不等于无数据 ——
    调用方一律用 `is None` 判断，禁止真值判断。
    """
    if not series:
        return None
    return Decimal(str(series[-1][1])).quantize(_PRECISION)


def avg_from_series(series, cutoff):
    """从日均序列取「近N月均价」= 窗口内日均值的算术平均。

    Args:
        series: [(date, day_avg), ...]，按 date 升序、同 date 已合并。
        cutoff: 窗口起点（含），早于该日期的点被忽略。
    Returns:
        Decimal（量化到 0.01）或 None（窗口内无数据）。

    判别性说明：这是「日均值的均值」，不是「记录级均值」。
    例如同日两条报价 (10, 20) 记为日均 15，另一日一条 30 记为日均 30，
    则结果 = (15 + 30) / 2 = 22.50，而记录级均值会是 (10+20+30)/3 = 20.00。
    测试 test_price_kernel.py 用这条数据钉住语义。
    """
    window = [day_avg for d, day_avg in series if d >= cutoff]
    if not window:
        return None
    total = sum((Decimal(str(v)) for v in window), Decimal('0'))
    return (total / len(window)).quantize(_PRECISION)


# ==========================================
# 批量查表
# ==========================================

class RawMaterialPriceLookup:
    """原材料价格批量查表 —— 一次装载，全局/单工厂/多工厂维度共用同一内核。

    典型用法（对比页 N 个配方）::

        lookup = RawMaterialPriceLookup.build(ids=raw_material_ids, months=6)
        lookup.latest(rm)          # 单条，复用已装载的数据
        lookup.avg_map()           # 批量 {rm_id: Decimal|None}
        lookup.avg_map(plant)      # 同上，限定单个工厂

    两种装载方式：

        build(ids=..., materials=..., months=...)   一次聚合查询覆盖全部 (材料×工厂×日期)
        from_materials(materials, months=...)       消费已 prefetch 的 price_records，0 条新查询

    内部统一物化为 rows = [(rm_id, plant_id, date, day_avg), ...]，
    之后所有维度都在内存里派生，装载只发生一次。
    """

    def __init__(self, months=None, ids=None):
        self._months = months
        self._material_ids = list(ids) if ids is not None else []
        self._rows = None
        self._series_cache = {}
        self._avg_cache = {}

    # ── 构造 ──

    @classmethod
    def build(cls, ids=None, materials=None, months=None):
        """从数据库装载。

        Args:
            ids: 原材料 id 可迭代对象。与 materials 二选一。
            materials: RawMaterial 实例可迭代对象（会取其 pk）。
            months: 均价窗口月数；None 时读 PriceAvgConfig。
        """
        if ids is None and materials is not None:
            ids = [m.pk for m in materials]
        return cls(months=months, ids=ids)

    @classmethod
    def from_materials(cls, materials, months=None):
        """从已 prefetch 的原材料实例装载，不产生新查询。

        要求调用方 prefetch 了 `price_records`（否则每个材料会打一次查询，
        批量路径的意义就没了）。
        """
        materials = list(materials)
        lookup = cls(months=months, ids=[m.pk for m in materials])
        rows = []
        for material in materials:
            # 只用 .all()，依赖 prefetch 缓存；filter/order_by 会绕过缓存重建查询
            buckets = defaultdict(lambda: [Decimal('0'), 0])
            for record in material.price_records.all():
                acc = buckets[(record.plant_id, record.date)]
                acc[0] += record.price
                acc[1] += 1
            rows.extend(
                (material.pk, plant_id, day, total / count)
                for (plant_id, day), (total, count) in buckets.items()
            )
        lookup._rows = rows
        return lookup

    # ── 配置 ──

    @property
    def months(self):
        """均价窗口月数。本实例内只解析一次，避免逐材料查配置表。"""
        if self._months is None:
            self._months = PriceAvgConfig.get().months
        return self._months

    @property
    def cutoff(self):
        """均价窗口起点（含）。"""
        return date.today() - timedelta(days=self.months * _DAYS_PER_MONTH)

    # ── 装载 ──

    def _load_rows(self):
        """物化 rows。build 路径打一次聚合查询，from_materials 路径已在构造时填好。"""
        if self._rows is not None:
            return self._rows
        if not self._material_ids:
            self._rows = []
            return self._rows
        qs = (
            RawMaterialPriceRecord.objects
            .filter(raw_material_id__in=self._material_ids)
            .values('raw_material_id', 'plant_id', 'date')
            .annotate(day_avg=Avg('price'))
        )
        self._rows = [
            (r['raw_material_id'], r['plant_id'], r['date'], r['day_avg'])
            for r in qs
        ]
        return self._rows

    # ── 维度派生 ──

    def series(self, plant=None):
        """取日均序列 {rm_id: [(date, day_avg), ...]}（按 date 升序）。

        Args:
            plant: None 为全局维度（同日跨工厂取均值）；Plant 实例或 plant_id
                   为单工厂维度。
        """
        key, plant_id = _plant_key(plant)
        cached = self._series_cache.get(key)
        if cached is not None:
            return cached

        buckets = defaultdict(lambda: defaultdict(lambda: [Decimal('0'), 0]))
        for rm_id, row_plant_id, day, day_avg in self._load_rows():
            if plant_id is not None and row_plant_id != plant_id:
                continue
            acc = buckets[rm_id][day]
            acc[0] += day_avg
            acc[1] += 1

        # 全局维度这里是对「各工厂当日均价」再求平均。等价于直接 Avg 全部记录，
        # 因为 unique_together(raw_material, plant, date) 保证每工厂每日恰好一条记录，
        # 所以每个工厂的当日均价权重相同。改动该约束会使这里失效。
        result = {
            rm_id: [(day, total / count) for day, (total, count) in sorted(by_day.items())]
            for rm_id, by_day in buckets.items()
        }
        self._series_cache[key] = result
        return result

    def plant_ids(self):
        """已装载数据中出现过的工厂 id 集合。"""
        return {row[1] for row in self._load_rows()}

    def known_material_ids(self):
        """本查表涉及的原材料 id 集合（含无价格记录者）。"""
        return set(self._material_ids) | {row[0] for row in self._load_rows()}

    # ── 单条读取 ──

    def latest(self, material, plant=None):
        """最新单价；没有报价 → None（不做跨维度兜底）。

        工厂维度没有该工厂的报价就是没有，不回落到全局。
        """
        rm_id = _rm_id(material)
        return latest_from_series(self.series(plant).get(rm_id) or [])

    def avg(self, material, plant=None):
        """近N月均价；回落链：窗口内有数据 → 窗口均值 → 该维度的 latest → None。"""
        rm_id = _rm_id(material)
        cache_key = (rm_id, _plant_key(plant)[0])
        if cache_key in self._avg_cache:
            return self._avg_cache[cache_key]
        value = avg_from_series(self.series(plant).get(rm_id) or [], self.cutoff)
        if value is None:
            value = self.latest(rm_id, plant)
        self._avg_cache[cache_key] = value
        return value

    # ── 批量读取 ──

    def latest_map(self, plant=None):
        """{rm_id: 最新单价}，覆盖 known_material_ids()。"""
        return {rm_id: self.latest(rm_id, plant) for rm_id in self.known_material_ids()}

    def avg_map(self, plant=None):
        """{rm_id: 近N月均价}，覆盖 known_material_ids()。"""
        return {rm_id: self.avg(rm_id, plant) for rm_id in self.known_material_ids()}

    def latest_map_by_plant(self):
        """{plant_id: {rm_id: 最新单价}}，覆盖数据中出现过的全部工厂。"""
        return {pid: self.latest_map(pid) for pid in self.plant_ids()}

    def avg_map_by_plant(self):
        """{plant_id: {rm_id: 近N月均价}}，覆盖数据中出现过的全部工厂。"""
        return {pid: self.avg_map(pid) for pid in self.plant_ids()}


# ==========================================
# 无状态门面
# ==========================================

class RawMaterialPriceService:
    """原材料价格服务门面 —— 供 models / views 调用的静态入口。

    所有方法都是薄包装，真正实现在上面的内核与查表类里；
    需要批量时直接用 RawMaterialPriceLookup，不要循环调单条方法。
    """

    @staticmethod
    def for_material(material):
        """单材料查表（每次调用新建，适合 property 按需取值）。"""
        return RawMaterialPriceLookup.from_materials([material])

    @staticmethod
    def for_materials(materials, months=None):
        """批量查表，消费已 prefetch 的 price_records。"""
        return RawMaterialPriceLookup.from_materials(materials, months=months)

    @staticmethod
    def for_ids(ids, months=None):
        """批量查表，按 id 一次性从库里取。"""
        return RawMaterialPriceLookup.build(ids=ids, months=months)

    @staticmethod
    def latest_price(material):
        """单材料最新单价。"""
        return RawMaterialPriceService.for_material(material).latest(material)

    @staticmethod
    def avg_price(material):
        """单材料近N月均价。"""
        return RawMaterialPriceService.for_material(material).avg(material)

    @staticmethod
    def latest_price_for_plant(material, plant):
        """单材料指定工厂的最新单价（该工厂当日均价）。"""
        return RawMaterialPriceService.for_material(material).latest(material, plant)

    @staticmethod
    def avg_price_for_plant(material, plant):
        """单材料指定工厂的近N月均价（窗口内日均值再平均）。"""
        return RawMaterialPriceService.for_material(material).avg(material, plant)

    # 内核函数透出，便于调用方与测试直接使用
    latest_from_series = staticmethod(latest_from_series)
    avg_from_series = staticmethod(avg_from_series)
