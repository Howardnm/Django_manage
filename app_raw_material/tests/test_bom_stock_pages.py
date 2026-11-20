"""三个页面上「库存」列的展示契约。

配方详情、配方过程、配色项目只读卡片共用同一套规则：
当前非限制库存跨工厂合计，四舍五入到整数，没有快照显示 -。
表头只有「库存」，数字用 fs-3，不右对齐。编辑态的色粉表单不加这一列。
"""

import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app_color_center.models import ColorMatchingTask
from app_formula.models import (
    ColorPowderBOM,
    ColorPowderBOMEntry,
    FormulaBOM,
    LabFormula,
)
from app_material.models import MaterialType
from app_project.models import Project
from app_raw_material.models import Plant, RawMaterial, RawMaterialStockSnapshot, RawMaterialType
from app_trial_production.models import ProductionOrder, ProductionOrderFormulaDetail

User = get_user_model()


class BomStockPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='stock-admin', email='stock@test.dev', password='x')
        self.client.force_login(self.user)

        self.material_type = MaterialType.objects.create(name='PA66基材')
        self.category = RawMaterialType.objects.create(name='色粉', code='PIGMENT')
        self.plant_a = Plant.objects.create(code='3011', name='上海')
        self.plant_b = Plant.objects.create(code='3020', name='昆山')

        self.rounded = self._material('STK-ROUND', 'A01005000021')
        self.down = self._material('STK-DOWN', 'A01005000022')
        self.zeroed = self._material('STK-ZERO', 'A01005000023')
        self.missing = self._material('STK-NONE', 'A01005000024')

        now = timezone.now()
        # 10.500 跨两个工厂，外加一条不该计入的旧批次和安全库存
        current_a = uuid.uuid4()
        self._snap(self.rounded, self.plant_a, batch=uuid.uuid4(), clabs='999.000',
                   eisbe='1.000', synced_at=now - timedelta(days=3))
        self._snap(self.rounded, self.plant_a, batch=current_a, loc='0001', clabs='5.250',
                   eisbe='80.000', synced_at=now)
        self._snap(self.rounded, self.plant_a, batch=current_a, loc='0002', clabs='4.250',
                   eisbe='80.000', synced_at=now)
        self._snap(self.rounded, self.plant_b, batch=uuid.uuid4(), clabs='1.000',
                   eisbe='9.000', synced_at=now)
        self._snap(self.down, self.plant_a, batch=uuid.uuid4(), clabs='10.400')
        self._snap(self.zeroed, self.plant_a, batch=uuid.uuid4(), clabs='0.000', eisbe='5.000')

        self.project = Project.objects.create(name='库存展示项目', manager=self.user)
        node = self.project.nodes.get(stage='RND')
        self.formula = LabFormula.objects.create(
            code='STK-F-001', name='库存配方', material_type=self.material_type,
            project=self.project, project_node=node, creator=self.user, version=1,
        )
        for raw in (self.rounded, self.down, self.zeroed, self.missing):
            FormulaBOM.objects.create(
                formula=self.formula, raw_material=raw, percentage=Decimal('2.500000'),
            )
        powder = ColorPowderBOM.objects.create(formula=self.formula)
        for raw in (self.rounded, self.down, self.zeroed, self.missing):
            ColorPowderBOMEntry.objects.create(
                color_powder_bom=powder, raw_material=raw, percentage=Decimal('2.500000'),
            )

    def _material(self, name, code):
        return RawMaterial.objects.create(
            name=name, model_name=name, warehouse_code=code, category=self.category,
        )

    def _snap(self, raw, plant, *, batch, loc='0001', clabs='0', eisbe='0', synced_at=None):
        snap = RawMaterialStockSnapshot.objects.create(
            sync_batch_id=batch,
            raw_material=raw,
            plant=plant,
            storage_location=loc,
            batch='B1',
            unrestricted_stock=Decimal(clabs),
            safety_stock=Decimal(eisbe),
        )
        if synced_at is not None:
            RawMaterialStockSnapshot.objects.filter(pk=snap.pk).update(synced_at=synced_at)
        return snap

    def _assert_stock_cell(self, html, material_name, expected):
        """比例数字后面的那个 fs-3 单元格才是库存。"""
        pattern = (
            rf'{re.escape(material_name)}[\s\S]{{0,800}}?'
            rf'class="fs-3">[\s\S]{{0,40}}?</td>\s*'
            rf'<td class="fs-3">\s*{re.escape(expected)}\s*</td>'
        )
        self.assertRegex(html, pattern, f'{material_name} 的库存应显示 {expected}')

    def _assert_form_stock(self, html, material_name, expected):
        """表单里库存跟在物料选择后面，单元格是 .bom-stock，不是详情页的 fs-3。"""
        pattern = (
            rf'{re.escape(material_name)}[\s\S]{{0,2000}}?'
            rf'class="bom-stock">\s*{re.escape(expected)}\s*</td>'
        )
        self.assertRegex(html, pattern, f'{material_name} 的表单库存应显示 {expected}')

    def _assert_column_contract(self, html, ratio_header):
        self.assertRegex(
            html,
            rf'{re.escape(ratio_header)}</th>\s*<th>库存</th>',
        )
        self.assertNotIn('text-end">库存', html)
        self.assertNotIn('text-end fs-3', html)
        # 旧批次 999 不能出现在库存单元格里；显示 11 就说明没把它加进去。
        self._assert_stock_cell(html, 'STK-ROUND', '11')
        self._assert_stock_cell(html, 'STK-DOWN', '10')
        self._assert_stock_cell(html, 'STK-ZERO', '0')
        self._assert_stock_cell(html, 'STK-NONE', '-')

    def test_formula_detail_bom_is_compact_and_shows_rounded_stock(self):
        resp = self.client.get(reverse('formula_detail', kwargs={'pk': self.formula.pk}))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()

        self.assertRegex(html, r'table-sm small[\s\S]{0,500}?比例/份数</th>\s*<th>库存</th>')
        self._assert_column_contract(html, '比例/份数')
        self.assertEqual(resp.context['stock_totals'][self.rounded.pk], Decimal('10.500'))
        self.assertEqual(resp.context['stock_totals'][self.zeroed.pk], Decimal('0.000'))
        self.assertNotIn(self.missing.pk, resp.context['stock_totals'])

    def test_formula_process_main_and_powder_bom_show_stock(self):
        url = reverse('project_formula_process', kwargs={'pk': self.project.pk})
        resp = self.client.get(f'{url}?stage=RND&round=1&formula_id={self.formula.pk}')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()

        self._assert_column_contract(html, '比例/份数')
        self.assertRegex(html, r'kg/100kg</span></th>\s*<th>库存</th>')
        self.assertGreaterEqual(html.count('<th>库存</th>'), 2)
        self.assertEqual(resp.context['stock_totals'][self.rounded.pk], Decimal('10.500'))
        self.assertNotIn(self.missing.pk, resp.context['stock_totals'])

    def test_formula_edit_both_modes_show_stock_after_percentage(self):
        url = reverse('formula_edit', kwargs={'pk': self.formula.pk})
        normal = self.client.get(url)
        self.assertEqual(normal.status_code, 200)
        normal_html = normal.content.decode()
        self.assertRegex(normal_html, r'比例/份数</span>[\s\S]{0,1600}?<th[^>]*>库存</th>')
        self._assert_form_stock(normal_html, 'STK-ROUND', '11')
        self._assert_form_stock(normal_html, 'STK-DOWN', '10')
        self._assert_form_stock(normal_html, 'STK-ZERO', '0')
        self._assert_form_stock(normal_html, 'STK-NONE', '-')

        self.formula.is_group_mode = True
        self.formula.save(update_fields=['is_group_mode'])
        grouped = self.client.get(url)
        self.assertEqual(grouped.status_code, 200)
        grouped_html = grouped.content.decode()
        self.assertRegex(grouped_html, r'比例/份数</span>[\s\S]{0,1600}?<th[^>]*>库存</th>')
        self.assertIn('替代组', grouped_html)
        self._assert_form_stock(grouped_html, 'STK-ROUND', '11')
        self._assert_form_stock(grouped_html, 'STK-NONE', '-')

    def test_formula_process_compare_mode_still_renders(self):
        url = reverse('project_formula_process', kwargs={'pk': self.project.pk})
        resp = self.client.get(f'{url}?compare=1')
        self.assertEqual(resp.status_code, 200)

    def test_color_center_readonly_card_is_compact_and_shows_stock(self):
        url = reverse('color_center:project', kwargs={'project_pk': self.project.pk})
        resp = self.client.get(f'{url}?stage=RND&round=1&formula_id={self.formula.pk}')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()

        self.assertNotContains(resp, 'id="bom-form"')
        self.assertRegex(html, r'table-sm small[\s\S]{0,500}?G/25KG</th>\s*<th>库存</th>')
        self._assert_column_contract(html, 'G/25KG')
        self.assertEqual(resp.context['stock_totals'][self.down.pk], Decimal('10.400'))

    def test_color_center_edit_form_shows_stock_next_to_ratio(self):
        url = reverse('color_center:project', kwargs={'project_pk': self.project.pk})
        resp = self.client.get(
            f'{url}?stage=RND&round=1&formula_id={self.formula.pk}&edit=1')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertContains(resp, 'id="bom-form"')
        self.assertRegex(html, r'G/25KG</th>\s*<th[^>]*>库存</th>')
        self._assert_form_stock(html, 'STK-ROUND', '11')
        self._assert_form_stock(html, 'STK-NONE', '-')
        self.assertEqual(resp.context['stock_totals'][self.rounded.pk], Decimal('10.500'))

    def test_color_center_open_task_stays_on_the_form(self):
        order = ProductionOrder.objects.create(
            creator=self.user, code='STK-O-001', trial_code=self.formula.code,
            quantity_planned=100, status=ProductionOrder.Status.EXTRUDING,
            project=self.project,
        )
        ProductionOrderFormulaDetail.objects.create(
            production_order=order, formula=self.formula,
            planned_quantity=100, needs_color_matching=True,
        )
        ColorMatchingTask.objects.create(
            production_order=order, status=ColorMatchingTask.Status.PENDING,
        )

        url = reverse('color_center:project', kwargs={'project_pk': self.project.pk})
        resp = self.client.get(f'{url}?formula_id={self.formula.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="bom-form"')
        self.assertContains(resp, '<th scope="col" style="width: 70px;">库存</th>')
        self._assert_form_stock(resp.content.decode(), 'STK-ROUND', '11')
