"""原材料自动补全（TomSelect 远程搜索）的回归测试。

配方编辑页 BOM 明细的「原材料」下拉走的是 common_utils 的通用
MaterialAutocompleteView + 本 app 注册的 'raw_material' 处理器。

修过两个问题：
1. 只按 名称/型号 匹配，内部物料编码（warehouse_code）虽然在候选文案里展示，
   却不在查询条件里 —— 输编码搜不到；
2. 候选文案不带价格，而选原材料时价格是主要判据之一。
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from app_raw_material.models import (
    Plant, RawMaterial, RawMaterialPriceRecord, RawMaterialStockSnapshot, RawMaterialType)

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

    def test_star_matches_any_length(self):
        results = self._search('RM-000*')
        self.assertEqual(
            sorted(r['value'] for r in results),
            sorted([self.material.pk, self.other.pk]))

    def test_question_mark_matches_one_character(self):
        results = self._search('RM-00012?')
        self.assertEqual([r['value'] for r in results], [self.material.pk])

    def test_star_in_the_middle(self):
        results = self._search('RM*123')
        self.assertEqual([r['value'] for r in results], [self.material.pk])

    def test_dot_is_literal_not_any_character(self):
        self.assertEqual(self._search('RM-000.23'), [])

    def test_wildcard_spans_name_model_code_and_plant(self):
        """pp*500n*A01*3011 要同时落在名称、型号、内部编码、工厂代码上。"""
        target = RawMaterial.objects.create(
            name='PP', model_name='HP500N/后面还有文字', warehouse_code='A01005000035',
            category=self.category)
        other_code = RawMaterial.objects.create(
            name='PP', model_name='HP500N/后面还有文字', warehouse_code='B02005000035',
            category=self.category)
        no_plant = RawMaterial.objects.create(
            name='PP', model_name='HP500N/后面还有文字', warehouse_code='A01005000099',
            category=self.category)
        other_plant = Plant.objects.create(code='3020', name='昆山工厂')
        target.plants.add(self.plant)
        other_code.plants.add(self.plant)

        def ids_for(query):
            return [row['value'] for row in self._search(query)]

        self.assertEqual(ids_for('pp*500n*3011'), [target.pk, other_code.pk])
        self.assertEqual(ids_for('pp*500n*A01*3011'), [target.pk])
        self.assertNotIn(other_code.pk, ids_for('pp*500n*A01*3011'))
        self.assertNotIn(target.pk, ids_for('pp*500n*3020'))
        self.assertIn(no_plant.pk, ids_for('pp*500n*'))
        self.assertNotIn(target.pk, ids_for('上海'))

        target.plants.add(other_plant)
        self.assertEqual(ids_for('pp*500n*A01*3011'), [target.pk])
        self.assertEqual(ids_for('3011'), [])

    def test_option_text_includes_price(self):
        """候选文案要带最新单价，且与其它附加信息一样用括号包裹。"""
        self.material.plants.add(self.plant)
        results = self._search('PA66')
        self.assertEqual(len(results), 1)
        text = results[0]['text']
        self.assertIn('PA66', text)
        self.assertIn('2600', text)
        self.assertIn('(树脂)', text)
        self.assertIn('(RM-000123)', text)
        self.assertIn('(3011)', text)
        self.assertNotIn('上海工厂', text)
        self.assertIn('(¥12.50)', text)
        # 工厂插在编码之后、价格之前
        self.assertLess(text.index('(3011)'), text.index('(¥12.50)'))
        self.assertLess(text.index('(RM-000123)'), text.index('(3011)'))

    def test_option_text_joins_plant_codes(self):
        """多个工厂合成一对括号，只显示代码，顿号分隔，按代码排序。"""
        other = Plant.objects.create(code='2010', name='昆山工厂')
        self.material.plants.add(self.plant, other)
        text = self._search('PA66')[0]['text']
        self.assertIn('(2010、3011)', text)
        self.assertNotIn('(2010)', text)
        self.assertNotIn('(3011)', text)
        self.assertNotIn('昆山工厂', text)
        self.assertNotIn('上海工厂', text)

    def test_material_without_price_still_listed(self):
        """没有报价的原材料也要能搜到，只是文案里不带价格。"""
        results = self._search('玻璃纤维')
        self.assertEqual(len(results), 1)
        self.assertIn('玻璃纤维', results[0]['text'])
        self.assertNotIn('¥', results[0]['text'])
        self.assertNotIn('3011', results[0]['text'])

    def test_option_includes_rounded_stock_qty(self):
        """候选项带当前非限制库存的整数。没有快照是 null，不能收成 0。"""
        now = timezone.now()
        current = uuid.uuid4()
        RawMaterialStockSnapshot.objects.create(
            sync_batch_id=uuid.uuid4(), raw_material=self.material, plant=self.plant,
            unrestricted_stock=Decimal('999.000'), safety_stock=Decimal('1.000'),
        ).pk
        old = RawMaterialStockSnapshot.objects.order_by('-pk').first()
        RawMaterialStockSnapshot.objects.filter(pk=old.pk).update(synced_at=now - timedelta(days=2))
        RawMaterialStockSnapshot.objects.create(
            sync_batch_id=current, raw_material=self.material, plant=self.plant,
            storage_location='0001', unrestricted_stock=Decimal('10.500'),
            safety_stock=Decimal('80.000'),
        )
        RawMaterialStockSnapshot.objects.create(
            sync_batch_id=uuid.uuid4(), raw_material=self.other, plant=self.plant,
            unrestricted_stock=Decimal('0.000'),
        )

        by_id = {row['value']: row for row in self._search('RM-000')}
        self.assertEqual(by_id[self.material.pk]['stock_qty'], 11)
        self.assertEqual(by_id[self.other.pk]['stock_qty'], 0)

        bare = RawMaterial.objects.create(
            name='无库存', model_name='NONE', warehouse_code='RM-000555',
            category=self.category)
        self.assertIsNone(self._search('RM-000555')[0]['stock_qty'])
        self.assertEqual(bare.warehouse_code, 'RM-000555')

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
