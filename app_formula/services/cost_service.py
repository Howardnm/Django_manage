"""配方成本核算服务 — 全项目唯一的「Σ 加权 + LOCF 时间线」实现。

## 为什么需要这个模块

「成本 = Σ(价格 × 份数) / Σ份数」这条算术在项目里曾经有 5 份拷贝：

    LabFormula.calculate_cost()              最新单价加权，写回 cost_predicted
    LabFormula.unit_cost                     property，近N月均价加权
    LabFormula.get_price_trend()             时间线，内联在 LOCF 循环里
    LabFormula.get_price_trend_for_plant()   同上，第 4 份
    LabFormula.calculate_cost_for_plant()
    LabFormula.get_unit_cost_for_plant()     第 5 份
    common_utils/serializers/compare.py 的 _compute_unit_cost / _compute_cp_cost

再加上各自不同的缺价处理（有的「稀释」、有的返回 None），口径必然漂移。
本模块把它收敛成一个内核 `weighted_unit_cost`，其余全是薄包装。

## 三个成本口径

    预测成本 predicted = 用「最新单价」加权         → LabFormula.cost('latest')
    近N月均价 unit      = 用「近N月均价」加权       → LabFormula.unit_cost
    色粉成本 powder     = Σ(份数 × 最新单价) / 100  → 色粉按主配方 100 份折算

其中「最新单价」「近N月均价」的口径定义在 app_raw_material/services/price_service.py，
本模块不重复实现价格聚合。

## 成本不落库

三种口径都是读取时实时算出来的，模型上没有任何成本列。
（历史上 `cost_predicted` 是物化列，靠 RawMaterial 的价格信号级联重算维护 ——
 因为「直接写价格记录」不走那条信号，物化值与实时值会长期不自洽，已删除。）
代价是分页列表无法在 SQL 层按成本排序，所以不提供该排序。
用过 `prime()` 预热的实例持有的是**请求级**价格快照。

## 缺价处理（严格模式）

任一「非 0% 的 BOM 行」查不到价格 → 整个成本返回 None（不下结论）。
0% 的行对成本没有贡献，缺价也不影响结果，因此不参与判断。

旧实现是「稀释」：缺价行计入分母、不计分子，于是会静默报出一个偏低的假成本。
本次统一为严格模式 —— 成本显示为空，而不是显示一个错的数。

## 循环 import 约束

本模块顶层 import app_raw_material 的 service；`app_formula/models.py` 只在
**函数体内**延迟 import 本模块。反向的顶层 import 会成环，勿改。

导出: FormulaCostCalculator, FormulaCostService, weighted_unit_cost, cost_timeline。
"""

import calendar
import logging
from decimal import Decimal

from app_raw_material.services import RawMaterialPriceLookup

logger = logging.getLogger(__name__)

_PRECISION = Decimal('0.01')

# 色粉按「主配方 100 份」折算 —— 与 ColorPowderBOM 的业务定义一致
_COLOR_POWDER_BASE = Decimal('100')


# ==========================================
# 纯算术内核（无 ORM 依赖，可 SimpleTestCase 覆盖）
# ==========================================

def _weighted(pairs):
    """加权平均内核 —— 全项目唯一的 Σ 实现。

    Args:
        pairs: 可迭代的 (份数, 价格) 二元组。价格为 None 表示该行查不到价格。
    Returns:
        Decimal（量化到 0.01）或 None。

    契约：
        - None 表示「算不出来」：任一非 0 份数的行缺价，或总份数 <= 0
        - Decimal('0.00') 是有效结果，不等于 None —— 调用方一律用 `is None` 判断
    """
    total_amount = Decimal('0')
    total_parts = Decimal('0')
    for percentage, price in pairs:
        parts = Decimal(str(percentage or 0))
        total_parts += parts
        if parts == 0:
            continue  # 0 份的行对成本无贡献，缺价也不影响结果
        if price is None:
            return None
        total_amount += Decimal(str(price)) * parts
    if total_parts <= 0:
        return None
    return (total_amount / total_parts).quantize(_PRECISION)


def weighted_unit_cost(bom_lines, price_of):
    """按 BOM 份数加权求单位成本。

    Args:
        bom_lines: FormulaBOM 可迭代对象（只有 .percentage 与 .raw_material_id 被用到）。
        price_of: callable(line) -> Decimal | None，返回该行的单价；None 表示缺价。
    Returns:
        Decimal（元/kg，量化到 0.01）或 None（缺价 / 无有效份数）。
    """
    return _weighted((line.percentage, price_of(line)) for line in bom_lines)


def cost_timeline(bom_lines, series_of):
    """构建配方单位成本时间线（LOCF：某日价格取该日之前最近一次报价）。

    Args:
        bom_lines: FormulaBOM 可迭代对象。
        series_of: callable(line) -> [(date, price), ...]，按 date 升序的日均价序列。
    Returns:
        [[timestamp_ms:int, cost:float], ...] 按日期升序。
        任一非 0 份数的行在某个日期前无报价 → 该日期整点不输出。

    说明：float 转换只在这个 JSON 边界发生（返回值直接喂 Highcharts），
    内部计算全程 Decimal。日期的价格取「日均值」而非「当日最后一条记录」，
    这样同一天有多条报价时走势是确定性的。
    """
    lines = [(line, series_of(line)) for line in bom_lines]
    if not lines:
        return []

    all_dates = set()
    for _, series in lines:
        all_dates.update(day for day, _ in series)
    if not all_dates:
        return []

    trend = []
    for day in sorted(all_dates):
        # LOCF：series 升序，取最后一个 date <= day 的价格
        prices = []
        for line, series in lines:
            price = None
            for record_date, record_price in series:
                if record_date <= day:
                    price = record_price
                else:
                    break
            prices.append((line.percentage, price))
        cost = _weighted(prices)
        if cost is not None:
            trend.append([calendar.timegm(day.timetuple()) * 1000, float(cost)])
    return trend


# ==========================================
# 成本计算器
# ==========================================

class FormulaCostCalculator:
    """配方成本核算唯一入口 —— N 个配方共用一次价格查表。

    典型用法（对比页 / 列表页）::

        calc = FormulaCostCalculator.for_formulas(formulas).prime()
        calc.unit_cost(f)          # 单条
        calc.predicted_cost(f)     # 单条
        calc.powder_cost(f.color_powder_bom)

    `prime()` 把计算器挂到每个配方实例上（`_cost_calculator`），
    于是模板里裸调 `f.unit_cost` 也能复用同一份价格数据，而不是各自重查。
    """

    def __init__(self, prices, formulas=None):
        self._prices = prices
        self._formulas = list(formulas) if formulas is not None else []

    # ── 构造 ──

    @classmethod
    def for_formulas(cls, formulas, months=None, extra_raw_material_ids=None):
        """收集这批配方涉及的全部原材料，一次装载价格，并自动预热。

        预热让模板里的裸 `f.unit_cost` 也能复用同一份价格数据。

        Args:
            extra_raw_material_ids: 额外的原材料 id。对比页会把「作为对比列出现的
                原材料」也一起装载 —— 它们不属于任何配方，但同样需要价格。
        """
        formulas = list(formulas)
        raw_material_ids = set(extra_raw_material_ids or ())
        for formula in formulas:
            for line in formula.bom_lines.all():
                raw_material_ids.add(line.raw_material_id)
            powder = getattr(formula, 'color_powder_bom', None)
            if powder is not None:
                for entry in powder.entries.all():
                    raw_material_ids.add(entry.raw_material_id)
        calculator = cls(
            RawMaterialPriceLookup.build(ids=raw_material_ids, months=months),
            formulas=formulas,
        )
        return calculator.prime()

    @classmethod
    def for_powder(cls, powder, months=None):
        """为单个色粉配比表建计算器。

        只装载色粉条目涉及的原材料，不牵动所属配方的主 BOM
        （因此不会为了取 self.formula 额外打一次查询）。
        """
        if powder is None or powder.pk is None:
            return cls(RawMaterialPriceLookup.build(ids=[]))
        return cls(RawMaterialPriceLookup.build(
            ids=[entry.raw_material_id for entry in powder.entries.all()],
            months=months,
        ))

    @classmethod
    def from_lookup(cls, prices, formulas=None):
        """直接复用已有的价格查表。传 formulas 时一并预热。"""
        calculator = cls(prices, formulas=formulas)
        return calculator.prime() if formulas else calculator

    @property
    def prices(self):
        """底层价格查表（供对比表列头等需要单价的地方使用）。"""
        return self._prices

    def prime(self, formulas=None):
        """把自身挂到每个配方（及其色粉配比表）上，消除模板侧的 N+1。

        Args:
            formulas: 要预热的配方；省略时用 for_formulas 记录的那批。

        Returns: self（便于链式调用）

        ⚠ 挂上去的价格快照是**请求级**的：预热之后若又改了价格记录，
        这些实例上的成本不会自动更新。视图预热 → 渲染的用法没问题；
        不要在长生命周期的地方复用被预热过的实例。
        """
        for formula in (formulas if formulas is not None else self._formulas):
            formula._cost_calculator = self
            powder = getattr(formula, 'color_powder_bom', None)
            if powder is not None:
                powder._cost_calculator = self
        return self

    # ── 各成本口径 ──

    def predicted_cost(self, formula, plant=None):
        """预测成本 —— 用最新单价加权（对应 LabFormula.cost_predicted）。"""
        return weighted_unit_cost(
            formula.bom_lines.all(),
            lambda line: self._prices.latest(line.raw_material_id, plant),
        )

    def unit_cost(self, formula, plant=None):
        """近N月均价成本 —— 用 avg_price 加权，窗口空时回落最新单价。"""
        return weighted_unit_cost(
            formula.bom_lines.all(),
            lambda line: self._prices.avg(line.raw_material_id, plant),
        )

    def total_cost(self, formula, plant=None):
        """配方的最新口径总成本 = 主BOM预测成本 + 色粉预测成本（元/kg）。

        色粉部分的两条规则，与单项的严格模式保持一致：
          - 没有色粉配比表 → 按 0 计（「没配色粉」不等于「算不出来」）
          - 有色粉配比表但有条目缺价 → 返回 None
        主BOM 缺价同样返回 None —— 宁可显示「算不出来」，
        也不给出一个漏掉色粉的偏低总成本。
        """
        main_cost = self.predicted_cost(formula, plant)
        if main_cost is None:
            return None
        powder = getattr(formula, 'color_powder_bom', None)
        if powder is None:
            return main_cost
        powder_cost = self.powder_cost(powder, plant)
        if powder_cost is None:
            return None
        return main_cost + powder_cost

    def powder_cost(self, powder, plant=None):
        """色粉成本 = Σ(份数 × 最新单价) / 100，单位 元/kg 主配方。

        Args:
            powder: ColorPowderBOM 实例；None 或未保存时返回 None。
        """
        if powder is None or powder.pk is None:
            return None
        total = Decimal('0')
        has_valid_entry = False
        for entry in powder.entries.all():
            parts = Decimal(str(entry.percentage or 0))
            if parts == 0:
                continue
            price = self._prices.latest(entry.raw_material_id, plant)
            if price is None:
                return None  # 严格模式
            total += parts * Decimal(str(price))
            has_valid_entry = True
        if not has_valid_entry:
            return None
        return (total / _COLOR_POWDER_BASE).quantize(_PRECISION)

    # ── 时间线 ──

    def trend(self, formula, plant=None):
        """配方单位成本时间线（LOCF，按日均价）。"""
        series_map = self._prices.series(plant)
        return cost_timeline(
            formula.bom_lines.all(),
            lambda line: series_map.get(line.raw_material_id) or [],
        )

    def trend_by_plant(self, formula, plants):
        """{工厂显示名: 时间线}，仅保留至少 2 个数据点的工厂。

        复用同一份价格查表，避免「每个工厂 × 每个 BOM 行」各打一次查询。
        """
        trends = {}
        for plant in plants:
            series = self.trend(formula, plant)
            if len(series) >= 2:
                trends[str(plant)] = series
        return trends


# ==========================================
# 无状态门面
# ==========================================

class FormulaCostService:
    """配方成本服务门面 —— 外部的静态入口。

    需要按配方取成本时优先用 FormulaCostCalculator（可批量复用价格数据）；
    这里只提供不持有状态的内核函数与一次性便捷方法。
    """

    @staticmethod
    def for_formulas(formulas, months=None):
        return FormulaCostCalculator.for_formulas(formulas, months=months)

    @staticmethod
    def for_formula(formula, months=None):
        return FormulaCostCalculator.for_formulas([formula], months=months)

    # 内核函数透出，便于调用方与测试直接使用
    weighted_unit_cost = staticmethod(weighted_unit_cost)
    cost_timeline = staticmethod(cost_timeline)
