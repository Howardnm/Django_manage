"""成本核算集成测试 —— 需要数据库。

这组测试是「防止再次分叉」的核心：它用真实 ORM 数据把
「原材料价格口径」→「配方成本口径」→「对比表序列化」整条链路钉死。
历史上这条链路的每个环节都各有一套实现，改一处忘一处就会静默出错。

注意：日期一律相对 `date.today()` 构造，因为均价窗口是
`PriceAvgConfig.months * 30` 天，写死日期会在窗口滑走后失效。
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from app_formula.models import ColorPowderBOM, ColorPowderBOMEntry, FormulaBOM, LabFormula
from app_formula.services import FormulaCostCalculator
from app_material.models import MaterialType
from app_raw_material.models import Plant, RawMaterial, RawMaterialPriceRecord, RawMaterialType

D_OLD = date.today() - timedelta(days=10)
D_NEW = date.today() - timedelta(days=1)


class CostIntegrationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='cost_tester', password='x')
        cls.material_type = MaterialType.objects.create(name='PA66')
        cls.category = RawMaterialType.objects.create(name='树脂', order=1)

        cls.plant_a = Plant.objects.create(code='1011', name='上海')
        cls.plant_b = Plant.objects.create(code='2011', name='昆山')

        cls.rm_a = RawMaterial.objects.create(name='PA66', category=cls.category)
        cls.rm_b = RawMaterial.objects.create(name='玻纤', category=cls.category)
        cls.rm_no_price = RawMaterial.objects.create(name='未报价料', category=cls.category)

        # rm_a: 旧日两个工厂 (10, 20) → 日均 15；新日一个工厂 30 → 日均 30
        RawMaterialPriceRecord.objects.create(
            raw_material=cls.rm_a, plant=cls.plant_a, price=Decimal('10'), date=D_OLD)
        RawMaterialPriceRecord.objects.create(
            raw_material=cls.rm_a, plant=cls.plant_b, price=Decimal('20'), date=D_OLD)
        RawMaterialPriceRecord.objects.create(
            raw_material=cls.rm_a, plant=cls.plant_a, price=Decimal('30'), date=D_NEW)

        # rm_b: 只有旧日一个价
        RawMaterialPriceRecord.objects.create(
            raw_material=cls.rm_b, plant=cls.plant_a, price=Decimal('5'), date=D_OLD)

        cls.formula = LabFormula.objects.create(
            name='成本测试配方', material_type=cls.material_type, creator=cls.user)
        FormulaBOM.objects.create(formula=cls.formula, raw_material=cls.rm_a, percentage=Decimal('60'))
        FormulaBOM.objects.create(formula=cls.formula, raw_material=cls.rm_b, percentage=Decimal('40'))

        cls.powder = ColorPowderBOM.objects.create(formula=cls.formula)
        ColorPowderBOMEntry.objects.create(
            color_powder_bom=cls.powder, raw_material=cls.rm_b, percentage=Decimal('5'))

        # 含一个无报价原材料的配方 → 成本不可计算
        cls.broken_formula = LabFormula.objects.create(
            name='缺价配方', material_type=cls.material_type, creator=cls.user)
        FormulaBOM.objects.create(
            formula=cls.broken_formula, raw_material=cls.rm_a, percentage=Decimal('50'))
        FormulaBOM.objects.create(
            formula=cls.broken_formula, raw_material=cls.rm_no_price, percentage=Decimal('50'))

    # ── 原材料价格口径 ──

    def test_latest_price_is_latest_day_cross_plant_average(self):
        # 最新日期只有 plant_a 报价 30
        self.assertEqual(self.rm_a.latest_price, Decimal('30.00'))
        self.assertEqual(self.rm_b.latest_price, Decimal('5.00'))

    def test_avg_price_is_mean_of_daily_means(self):
        # rm_a 日均序列 [15, 30] → (15 + 30) / 2 = 22.50
        # 若误用记录级均值会是 (10 + 20 + 30) / 3 = 20.00
        self.assertEqual(self.rm_a.avg_price, Decimal('22.50'))

    def test_material_without_prices_has_no_price(self):
        self.assertIsNone(self.rm_no_price.latest_price)
        self.assertIsNone(self.rm_no_price.avg_price)

    def test_single_price_latest_equals_avg(self):
        # 窗口空时的回落链：avg → latest
        self.assertEqual(self.rm_b.avg_price, Decimal('5.00'))

    def test_plant_scoped_prices_use_same_algorithm(self):
        # plant_a 日均序列 [10, 30] → 20.00；最新 = 30
        self.assertEqual(self.rm_a.latest_price_for_plant(self.plant_a), Decimal('30.00'))
        self.assertEqual(self.rm_a.avg_price_for_plant(self.plant_a), Decimal('20.00'))
        # plant_b 只有旧日 20
        self.assertEqual(self.rm_a.latest_price_for_plant(self.plant_b), Decimal('20.00'))

    def test_plant_without_records_returns_none(self):
        self.assertIsNone(self.rm_b.latest_price_for_plant(self.plant_b))
        self.assertIsNone(self.rm_b.avg_price_for_plant(self.plant_b))

    # ── 配方成本口径 ──

    def test_unit_cost_uses_avg_price(self):
        # (22.50 * 60 + 5.00 * 40) / 100 = 15.50
        self.assertEqual(self.formula.unit_cost, Decimal('15.50'))

    def test_predicted_cost_uses_latest_price(self):
        # (30.00 * 60 + 5.00 * 40) / 100 = 20.00
        self.assertEqual(self.formula.cost('latest'), Decimal('20.00'))

    def test_missing_price_makes_cost_uncomputable(self):
        # 严格模式：缺价不下结论，而不是把缺价行当成 0 算出偏低的成本
        self.assertIsNone(self.broken_formula.unit_cost)
        self.assertIsNone(self.broken_formula.cost('latest'))

    def test_cost_is_computed_live_from_price_records(self):
        """改价格后成本立即变化 —— 这正是删掉落库字段的目的。

        成本不再依赖任何信号/重算流程，所以「物化值与实时值不自洽」
        这一类 bug 不可能再出现。
        """
        self.assertEqual(self.formula.cost('latest'), Decimal('20.00'))

        RawMaterialPriceRecord.objects.create(
            raw_material=self.rm_a, plant=self.plant_a,
            price=Decimal('60'), date=D_NEW + timedelta(days=1))

        # 丢掉 prime() 挂上的价格快照 —— 等价于「新的一次请求」。
        # 挂了快照的实例是请求级的，看到的是装载那一刻的价格，不该跨请求复用。
        self.formula._cost_calculator = None

        # 不做任何字段刷新、不触发任何信号 —— 成本必须立刻反映新价格
        # (60 * 60 + 5 * 40) / 100 = 38.00
        self.assertEqual(self.formula.cost('latest'), Decimal('38.00'))

    # ── 时间线 ──

    def test_trend_uses_daily_means_and_locf(self):
        trend = self.formula.get_price_trend()
        self.assertEqual(len(trend), 2)
        # 旧日: (15 * 60 + 5 * 40) / 100 = 11.00；新日: (30 * 60 + 5 * 40) / 100 = 20.00
        self.assertEqual([point[1] for point in trend], [11.0, 20.0])

    def test_trend_by_plant_only_keeps_plants_with_enough_points(self):
        trends = self.formula.get_price_trend_by_plant()
        # 只有 plant_a 在两天都有报价（plant_b 只有一天，不满足 >= 2 个点）
        self.assertEqual(set(trends), {str(self.plant_a)})

    def test_trend_for_plant_without_records_is_empty(self):
        self.assertEqual(self.formula.get_price_trend(self.plant_b), [])

    # ── 色粉成本 ──

    def test_color_powder_cost_returns_decimal(self):
        # 5 * 5.00 / 100 = 0.25
        self.assertEqual(self.powder.cost, Decimal('0.25'))
        self.assertIsInstance(self.powder.cost, Decimal)

    # ── 委托的一致性：计算器与 Model 必须同源 ──

    def test_calculator_agrees_with_model_properties(self):
        # prime() 会把计算器挂到实例上缓存价格；测试里显式清掉，
        # 避免上一个用例挂的陈旧计算器泄漏到本次断言
        self.formula._cost_calculator = None
        self.broken_formula._cost_calculator = None

        calculator = FormulaCostCalculator.for_formulas(
            [self.formula, self.broken_formula]).prime()

        self.assertEqual(calculator.unit_cost(self.formula), self.formula.unit_cost)
        self.assertEqual(calculator.predicted_cost(self.formula), self.formula.cost('latest'))
        self.assertEqual(calculator.trend(self.formula), self.formula.get_price_trend())
        self.assertEqual(calculator.powder_cost(self.powder), self.powder.cost)
        self.assertIsNone(calculator.unit_cost(self.broken_formula))

    def test_model_total_cost_property(self):
        """LabFormula.total_cost 是计算器 total_cost 的薄委托。"""
        # 清掉可能被上一个用例挂上的价格快照
        self.formula._cost_calculator = None
        self.broken_formula._cost_calculator = None

        calculator = FormulaCostCalculator.for_formulas([self.formula])
        self.assertEqual(calculator.total_cost(self.formula), self.formula.total_cost)

        # 20.00（主BOM，最新单价加权）+ 0.25（色粉）= 20.25
        self.assertEqual(self.formula.total_cost, Decimal('20.25'))

        # 主BOM 缺价 → 合计也拿不出来，而不是只报主BOM部分
        self.assertIsNone(self.broken_formula.total_cost)

    def test_price_lookup_agrees_with_material_properties(self):
        calculator = FormulaCostCalculator.for_formulas([self.formula])
        prices = calculator.prices
        for material in (self.rm_a, self.rm_b, self.rm_no_price):
            self.assertEqual(prices.latest(material.pk), material.latest_price)
            self.assertEqual(prices.avg(material.pk), material.avg_price)

    # ── 对比表序列化：与 Model 同口径 ──

    def test_serialize_compare_cost_sections_match_model(self):
        from common_utils.comparison_matrix import build_compare_matrices
        from common_utils.serializers.compare import serialize_compare

        columns = [{'type': 'formula', 'obj': self.formula}]
        matrices = build_compare_matrices(columns)
        data = serialize_compare(columns, matrices, 6, None)

        sections = {s['key']: s for s in data['sections']}
        avg_value = sections['avg_price']['rows'][0]['values'][0]['v']
        cp_value = sections['cp_cost']['rows'][0]['values'][0]['v']

        self.assertEqual(Decimal(avg_value), self.formula.unit_cost)
        self.assertEqual(Decimal(cp_value), self.powder.cost)

    def test_serialize_compare_total_cost_row(self):
        """最新总成本 = 主BOM预测成本 + 色粉预测成本，缺价时按严格模式留空。

        三种组合都要钉住：
          1. 两项都算得出     → 求和
          2. 主BOM算得出、没有色粉配比表 → 就等于主BOM成本（色粉按 0 计，不是「算不出来」）
          3. 主BOM 缺价       → 整行为空
        """
        from common_utils.comparison_matrix import build_compare_matrices
        from common_utils.serializers.compare import serialize_compare

        # 情形 2：有 BOM 行且都能定价，但没有色粉配比表
        plain = LabFormula.objects.create(
            name='无配色配方', material_type=self.material_type, creator=self.user)
        FormulaBOM.objects.create(formula=plain, raw_material=self.rm_a, percentage=Decimal('100'))

        columns = [{'type': 'formula', 'obj': obj}
                   for obj in (self.formula, plain, self.broken_formula)]
        matrices = build_compare_matrices(columns)
        data = serialize_compare(columns, matrices, 6, None)
        sections = {s['key']: s for s in data['sections']}

        total = sections['total_cost']['rows'][0]['values']
        main = sections['cost']['rows'][0]['values']
        powder = sections['cp_cost']['rows'][0]['values']

        # 情形 1：20.00（主BOM）+ 0.25（色粉）= 20.25
        self.assertEqual(Decimal(main[0]['v']), Decimal('20.00'))
        self.assertEqual(Decimal(powder[0]['v']), Decimal('0.25'))
        self.assertEqual(Decimal(total[0]['v']), Decimal('20.25'))
        self.assertFalse(total[0]['empty'])

        # 情形 2：无色粉配比表 → 总成本 == 主BOM成本
        self.assertTrue(powder[1]['empty'])
        self.assertEqual(Decimal(total[1]['v']), Decimal(main[1]['v']))

        # 情形 3：主BOM 缺价 → 总成本留空，而不是给出一个偏低的部分和
        self.assertTrue(main[2]['empty'])
        self.assertTrue(total[2]['empty'])
