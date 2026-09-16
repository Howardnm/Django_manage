"""原材料自动补全（TomSelect 远程搜索）的回归测试。

配方编辑页 BOM 明细的「原材料」下拉走的是 common_utils 的通用
MaterialAutocompleteView + 本 app 注册的 'raw_material' 处理器。

修过两个问题：
1. 只按 名称/型号 匹配，内部物料编码（warehouse_code）虽然在候选文案里展示，
   却不在查询条件里 —— 输编码搜不到；
2. 候选文案不带价格，而选原材料时价格是主要判据之一。
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from app_raw_material.models import (
    Plant, RawMaterial, RawMaterialPriceRecord, RawMaterialType)

User = get_user_model()


class RawMaterialAutocompleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='rm_auto', email='rm@test.local', password='x')
        self.client.force_login(self.user)

        self.category = RawMaterialType.objects.create(name='树脂')
        self.material = RawMaterial.objects.create(
            name='PA66', model_name='2600', warehouse_code='RM-000123',
            category=self.category)
        self.other = RawMaterial.objects.create(
            name='玻璃纤维', model_name='GF-30', warehouse_code='RM-000999',
            category=self.category)

        self.plant = Plant.objects.create(code='3011', name='上海工厂')
        RawMaterialPriceRecord.objects.create(
            raw_material=self.material, plant=self.plant,
            price=Decimal('12.50'), date=timezone.localdate())

    def _search(self, query):
        resp = self.client.get(
            reverse('material_api_search'),
            {'model': 'raw_material', 'q': query},
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_search_by_warehouse_code(self):
        """按内部物料编码搜索要能命中（编码是主要查找方式之一）。"""
        results = self._search('RM-000123')
        self.assertEqual([r['value'] for r in results], [self.material.pk])

    def test_search_by_partial_code(self):
        """编码用包含匹配，不是前缀/精确匹配。"""
        results = self._search('000123')
        self.assertEqual([r['value'] for r in results], [self.material.pk])

    def test_search_by_code_prefix_matches_all(self):
        results = self._search('RM-000')
        self.assertEqual(
            sorted(r['value'] for r in results),
            sorted([self.material.pk, self.other.pk]))

    def test_search_by_name_and_model_still_works(self):
        self.assertEqual([r['value'] for r in self._search('PA66')], [self.material.pk])
        self.assertEqual([r['value'] for r in self._search('2600')], [self.material.pk])

    def test_option_text_includes_price(self):
        """候选文案要带最新单价，且与其它附加信息一样用括号包裹。"""
        results = self._search('PA66')
        self.assertEqual(len(results), 1)
        text = results[0]['text']
        self.assertIn('PA66', text)
        self.assertIn('2600', text)
        self.assertIn('(树脂)', text)
        self.assertIn('(RM-000123)', text)
        self.assertIn('(¥12.50)', text)

    def test_material_without_price_still_listed(self):
        """没有报价的原材料也要能搜到，只是文案里不带价格。"""
        results = self._search('玻璃纤维')
        self.assertEqual(len(results), 1)
        self.assertIn('玻璃纤维', results[0]['text'])
        self.assertNotIn('¥', results[0]['text'])

    def test_detail_url_is_injected(self):
        results = self._search('PA66')
        self.assertIn('url', results[0])

    def test_price_lookup_is_batched(self):
        """价格必须一次装载 —— 逐条查价在自动补全这种高频接口上是 N+1。

        断言的是不变式「候选数量增长而查询数不变」，而不是写死条数：
        后者会随会话/权限等无关实现的查询数变化而误报。
        """
        for i in range(5):
            material = RawMaterial.objects.create(
                name=f'PP{i}', warehouse_code=f'RM-1000{i}', category=self.category)
            RawMaterialPriceRecord.objects.create(
                raw_material=material, plant=self.plant,
                price=Decimal('5.00'), date=timezone.localdate())

        with CaptureQueriesContext(connection) as one_candidate:
            results_one = self._search('PA66')
        with CaptureQueriesContext(connection) as many_candidates:
            results_many = self._search('RM-10')

        self.assertEqual(len(results_one), 1)
        self.assertEqual(len(results_many), 5)
        self.assertTrue(all('(¥5.00)' in r['text'] for r in results_many))
        self.assertEqual(
            len(many_candidates), len(one_candidate),
            '5 条候选比 1 条候选多打了查询 —— 价格没有批量装载')
