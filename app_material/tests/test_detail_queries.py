"""材料详情页的查询数回归。

两处历史问题：

1. 「成熟配方」卡曾用 `material.get_mature_formulas()` 另起一个 queryset，
   返回的配方实例没有被 `FormulaCostCalculator` 预热，模板里的 `f.cost`
   于是逐个配方重建一次价格查表（bom_lines + color_powder_bom + 价格聚合
   + PriceAvgConfig，约 3.5 条/配方）。

2. 「技术文档」卡对同一材料连调三次 `attachment_url`（TDS / MSDS / RoHS），
   每次独立查一次附件表。

本测试从页面层面锁定：这两处都不随数据量增长。
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from app_attachment.models import Attachment
from app_formula.models import FormulaBOM, LabFormula
from app_material.models import MaterialLibrary, MaterialType
from app_project.models import Project
from app_raw_material.models import (Plant, RawMaterial, RawMaterialPriceRecord,
                                     RawMaterialType)
from app_user.models import ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()

# 单行 BOM：份数 100 × 单价 10.00 → 成本 10.00
UNIT_PRICE = Decimal('10.00')
EXPECTED_COST = '10.00'


class MaterialDetailQueryCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.material_type = MaterialType.objects.create(name='工程塑料')
        cls.rm_type = RawMaterialType.objects.create(name='树脂', code='RESIN')
        cls.plant = Plant.objects.create(code='3011', name='上海工厂')

    def setUp(self):
        role = UserRole.objects.create(code='ENGINEER', name='研发工程师')
        group = RoleGroup.objects.create(code='RND_Engineer_Team', name='研发工程师团队')
        group.roles.add(role)
        cfg = ModuleAccessConfig.objects.create(
            module_code='material', module_name='材料成品库',
            enforce_dept_isolation=False, enforce_group_isolation=False)
        cfg.role_groups.add(group)
        IdentityService.invalidate_cache()

        self.user = User.objects.create_user(
            username='viewer', email='viewer@test.dev', password='x')
        self.user.user_type = role
        self.user.save()
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_materiallibrary', 'change_materiallibrary'],
            content_type__app_label='app_material'))
        self.client.force_login(self.user)

        self.material = MaterialLibrary.objects.create(
            grade_name='DETAIL-QC', sap_material_code='A09000',
            category=self.material_type, creator=self.user)
        self.project = Project.objects.create(
            code='P-QC', name='查询数项目', manager=self.user, material=self.material)

    def _create_mature_formulas(self, count, start=0):
        """建 count 个成熟配方，每个带 1 行 BOM（原材料有价格记录）。

        start 用于分批创建时避开 unique_together('code', 'version')。
        """
        for i in range(start, start + count):
            rm = RawMaterial.objects.create(
                name=f'PA66-{i}', category=self.rm_type)
            RawMaterialPriceRecord.objects.create(
                raw_material=rm, plant=self.plant,
                price=UNIT_PRICE, date=date.today())
            formula = LabFormula.objects.create(
                name=f'成熟配方{i}', code=f'L-QC-{i}', material_type=self.material_type,
                project=self.project, is_mature=True, version=1, creator=self.user)
            FormulaBOM.objects.create(
                formula=formula, raw_material=rm, percentage=Decimal('100'))
        return count

    def _render_detail(self):
        """返回 (response, 捕获到的查询列表)。"""
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                reverse('material_detail', kwargs={'pk': self.material.pk}))
        self.assertEqual(resp.status_code, 200)
        return resp, ctx.captured_queries

    def test_query_count_does_not_grow_with_mature_formula_count(self):
        self._create_mature_formulas(1)
        _, one = self._render_detail()

        self._create_mature_formulas(4, start=1)  # 累计 5 个成熟配方
        resp, five = self._render_detail()

        # 预热失效时每个配方会额外打 3~4 条查询，这里必须基本持平
        self.assertLessEqual(
            len(five) - len(one), 2,
            f'成熟配方 1 → 5 个时查询数从 {len(one)} 涨到 {len(five)}，成本预热已失效')
        self.assertIn(EXPECTED_COST, resp.content.decode())

    def test_mature_card_still_renders_cost(self):
        """成熟配方卡必须照常显示成本值（预热复用不能改变口径）。"""
        self._create_mature_formulas(2)
        resp, _ = self._render_detail()
        html = resp.content.decode()

        self.assertIn('成熟配方 (2)', html)
        # 该 badge 只在成熟配方卡出现（关联配方卡用的是 text-orange/text-green）
        self.assertEqual(
            html.count(f'<span class="badge bg-teal-lt">¥{EXPECTED_COST}</span>'), 2)

    def test_project_card_does_not_query_nodes(self):
        """项目卡的进度/阶段读 Project 的冗余列，不该为 nodes 打查询。"""
        Project.objects.create(
            code='P-QC-2', name='第二项目', manager=self.user, material=self.material)

        _, queries = self._render_detail()

        hits = [q for q in queries if 'projectnode' in q['sql'].lower()]
        self.assertEqual(hits, [], '项目卡不应加载 ProjectNode')

    def test_attachment_documents_share_one_query(self):
        """技术文档三件套 + 附件面板：附件表只应被查一次。"""
        ct = ContentType.objects.get_for_model(MaterialLibrary)  # 预热，不混入统计
        for category in ('TDS', 'MSDS', 'RoHS'):
            Attachment.objects.create(
                content_type=ct, object_id=self.material.pk, file='x.pdf',
                category=category, uploader=self.user)

        resp, queries = self._render_detail()

        hits = [q for q in queries if 'app_attachment_attachment' in q['sql']]
        self.assertEqual(
            len(hits), 1,
            f'TDS/MSDS/RoHS + 面板应合计 1 条附件查询，实际 {len(hits)} 条')
        self.assertIn('TDS 物性表', resp.content.decode())
