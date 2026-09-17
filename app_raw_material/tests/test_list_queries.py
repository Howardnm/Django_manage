"""原材料相关列表页的查询数回归。

背景：文档列每行渲染 TDS / MSDS / RoHS 三个附件链接，旧实现是每行各查一次
（paginate_by=20，即每页 20 条白打）。现在模板在行循环前用
`{% attachment_prime ... %}` 一次查完整页的附件。

锁定目标：页面总查询数不随行数增长。这也连带守住视图侧的 prefetch
（价格 / 物性 / 适用体系）—— 它们一旦丢失，同样是每行一查。
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from app_attachment.models import Attachment
from app_material.models import MaterialType, MetricCategory, TestConfig
from app_raw_material.models import (Plant, RawMaterial, RawMaterialPriceRecord,
                                     RawMaterialProperty, RawMaterialType,
                                     Supplier)
from app_user.models import ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()

ROWS = 5


class RawMaterialPageQueryCountBase(TestCase):
    """共用的 RBAC 与造数据；子类实现 _render() 指向具体页面。"""

    @classmethod
    def setUpTestData(cls):
        cls.category = RawMaterialType.objects.create(name='树脂')
        cls.supplier = Supplier.objects.create(name='测试供应商')
        cls.plant = Plant.objects.create(code='3011', name='上海工厂')
        cls.sys_type = MaterialType.objects.create(name='工程塑料')
        cls.test_config = TestConfig.objects.create(
            category=MetricCategory.objects.create(name='力学性能', order=1),
            name='拉伸强度', standard='ISO 527', order=1, data_type='NUMBER')

    def setUp(self):
        role = UserRole.objects.create(code='ENGINEER', name='研发工程师')
        group = RoleGroup.objects.create(code='RND_Center_Engineer_Team', name='工程师团队')
        group.roles.add(role)
        cfg = ModuleAccessConfig.objects.create(
            module_code='raw_material', module_name='原材料/供应商',
            enforce_dept_isolation=False, enforce_group_isolation=False)
        cfg.role_groups.add(group)
        IdentityService.invalidate_cache()

        self.user = User.objects.create_user(username='viewer', password='x')
        self.user.user_type = role
        self.user.save()
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_rawmaterial', 'view_supplier'],
            content_type__app_label='app_raw_material'))
        self.client.force_login(self.user)

    def _make_rows(self, count, start=0):
        """建「数据齐全」的行：供应商、适用体系、物性、多工厂多条价格。"""
        for i in range(start, start + count):
            rm = RawMaterial.objects.create(
                name=f'RM-{i}', model_name=f'M{i}', category=self.category,
                supplier=self.supplier)
            rm.suitable_materials.add(self.sys_type)
            RawMaterialProperty.objects.create(
                raw_material=rm, test_config=self.test_config, value=25)
            for day in range(1, 4):
                RawMaterialPriceRecord.objects.create(
                    raw_material=rm, plant=self.plant,
                    price=10 + day, date=date(2026, 1, day))

    def _render(self):
        raise NotImplementedError

    def _queries(self, table):
        return lambda qs: [q for q in qs if table in q]

    def assert_query_count_is_flat(self):
        self._make_rows(1)
        self._render()  # 预热 RBAC 的 L1 缓存，结果丢弃

        _, one = self._render()
        self._make_rows(ROWS - 1, start=1)
        _, many = self._render()

        self.assertEqual(
            len(one), len(many),
            f'{ROWS} 行比 1 行多打了 {len(many) - len(one)} 条查询 —— 出现了每行一查')


class RawMaterialListQueryCountTests(RawMaterialPageQueryCountBase):
    """/raw-material/materials/"""

    def _render(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(reverse('raw_material_list'))
        self.assertEqual(resp.status_code, 200)
        return resp, [q['sql'] for q in ctx.captured_queries]

    def test_query_count_does_not_grow_with_row_count(self):
        self.assert_query_count_is_flat()

    def test_attachment_query_is_constant(self):
        """文档列的附件恒为 1 条查询（附件面板不查库、prime 一次查完整页）。"""
        self._make_rows(1)
        self._render()  # 预热

        _, one = self._render()
        self._make_rows(ROWS - 1, start=1)
        _, many = self._render()

        hits = self._queries('app_attachment_attachment')
        self.assertEqual(len(hits(one)), 1)
        self.assertEqual(len(hits(many)), 1)

    def test_document_links_still_render(self):
        """prime 只是换装载方式，不能把链接渲染丢了。"""
        self._make_rows(1)
        material = RawMaterial.objects.get(name='RM-0')
        tds = Attachment.objects.create(
            content_type=ContentType.objects.get_for_model(RawMaterial),
            object_id=material.pk, file='tds.pdf', category='TDS',
            uploader=self.user)

        resp, _ = self._render()

        self.assertIn(
            reverse('attachment:download', kwargs={'token': tds.download_token}),
            resp.content.decode())


class SupplierDetailQueryCountTests(RawMaterialPageQueryCountBase):
    """/raw-material/suppliers/<pk>/ —— 内嵌的原材料清单是同一套渲染。"""

    def _render(self):
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                reverse('raw_supplier_detail', kwargs={'pk': self.supplier.pk}))
        self.assertEqual(resp.status_code, 200)
        return resp, [q['sql'] for q in ctx.captured_queries]

    def test_query_count_does_not_grow_with_row_count(self):
        self.assert_query_count_is_flat()

    def test_suitable_materials_prefetched(self):
        """适用体系列曾漏了 prefetch，退化成每行一查。"""
        self._make_rows(ROWS)
        _, queries = self._render()

        hits = self._queries('suitable_materials')
        self.assertLessEqual(
            len(hits(queries)), 1,
            f'适用体系应一次取完，实际 {len(hits(queries))} 条')
