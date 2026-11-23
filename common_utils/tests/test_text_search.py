"""各远程下拉的通配符查询。

``*`` 任意长度，``?`` 一个字符。句点仍是字面量。
没有通配符时仍是包含匹配。
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from app_basic_research.models import ResearchProject
from app_material.models.material import (
    ApplicationScenario,
    MaterialCharacteristic,
    MaterialLibrary,
    MaterialType,
    MetricCategory,
    TestConfig,
)
from app_process.models import ProcessProfile
from app_project.models import Project
from app_raw_material.models import RawMaterial, RawMaterialType
from app_repository.models import Customer, OEM

User = get_user_model()


class WildcardAutocompleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='wild_admin', email='wild@test.local', password='x')
        self.client.force_login(self.user)

        category = RawMaterialType.objects.create(name='树脂')
        RawMaterial.objects.create(
            name='PA66', model_name='2600', warehouse_code='RM-000123', category=category)
        RawMaterial.objects.create(
            name='玻璃纤维', model_name='GF-30', warehouse_code='RM-000999', category=category)
        RawMaterial.objects.create(
            name='PP', model_name='HP500N/后面还有文字', warehouse_code='RM-PP-500',
            category=category)

        eng = MaterialType.objects.create(name='工程塑料')
        commodity = MaterialType.objects.create(name='通用塑料')
        MaterialLibrary.objects.create(
            grade_name='PA66-G30', manufacturer='上海基地',
            sap_material_code='SAP-100', category=eng)
        MaterialLibrary.objects.create(
            grade_name='PBT-G30', manufacturer='昆山基地',
            sap_material_code='SAP-200', category=commodity)

        ApplicationScenario.objects.create(name='汽车内饰')
        ApplicationScenario.objects.create(name='家电外壳')
        MaterialCharacteristic.objects.create(name='耐热')
        MaterialCharacteristic.objects.create(name='耐磨')
        TestConfig.objects.create(
            category=MetricCategory.objects.create(name='力学', order=1),
            name='拉伸强度', standard='ISO 527', order=1)
        TestConfig.objects.create(
            category=MetricCategory.objects.create(name='其他', order=2),
            name='密度', standard='ISO 1183', order=1)

        ProcessProfile.objects.create(name='双螺杆A')
        ProcessProfile.objects.create(name='单螺杆B')
        Project.objects.create(name='PP项目一', code='WILD-PP', manager=self.user)
        Project.objects.create(name='PA项目二', code='WILD-PA', manager=self.user)
        ResearchProject.objects.create(name='预研甲', code='BR-001', manager=self.user)
        ResearchProject.objects.create(name='预研乙', code='BR-002', manager=self.user)

        User.objects.create_user(username='pp_user', email='pp_user@test.local', password='x')
        User.objects.create_user(username='pa_user', email='pa_user@test.local', password='x')
        User.objects.create_user(
            username='pp_inactive', email='pp_inactive@test.local', password='x', is_active=False)

        Customer.objects.create(company_name='PP客户')
        Customer.objects.create(company_name='PA客户')
        OEM.objects.create(name='主机厂甲', short_name='甲')
        OEM.objects.create(name='主机厂乙', short_name='乙')
        User.objects.create_user(
            username='pp_sales', email='pp_sales@test.local', password='x', is_staff=True)
        User.objects.create_user(
            username='pa_sales', email='pa_sales@test.local', password='x', is_staff=False)

    def _search(self, model, query, **extra):
        params = {'model': model, 'q': query}
        params.update(extra)
        resp = self.client.get(reverse('material_api_search'), params)
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) else body
        return [row['text'] for row in rows]

    def _repo(self, model, query):
        resp = self.client.get(reverse('repo_api_search'), {'model': model, 'q': query})
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        return [row['text'] for row in resp.json()]

    def test_empty_query_returns_default_rows(self):
        rows = self._search('raw_material', '')
        self.assertTrue(rows)
        self.assertLessEqual(len(rows), 35)
        self.assertTrue(any('PA66' in text for text in rows))

    def test_raw_material_wildcards_and_plain_text(self):
        codes = self._search('raw_material', 'RM-000*')
        self.assertTrue(any('RM-000123' in text for text in codes))
        self.assertTrue(any('RM-000999' in text for text in codes))
        one = self._search('raw_material', 'RM-00012?')
        self.assertEqual(len(one), 1)
        self.assertIn('RM-000123', one[0])
        self.assertEqual(self._search('raw_material', 'RM-000.23'), [])
        plain = self._search('raw_material', 'PA66')
        self.assertEqual(len(plain), 1)
        self.assertIn('PA66', plain[0])

    def test_wildcard_spans_name_and_model(self):
        """名称是 PP、型号里 500N 后面还有文字时，通配要跨字段拼在一起。"""
        for query in ('PP*500n', 'PP*500n*', 'PP**500n', 'PP**500n*'):
            hit = self._search('raw_material', query)
            self.assertTrue(any('HP500N' in text for text in hit), query)
        self.assertTrue(any('HP500N' in text for text in self._search('raw_material', '500n')))

        def query_count():
            with CaptureQueriesContext(connection) as ctx:
                self._search('raw_material', 'PP*500n*')
            return len(ctx)

        before = query_count()
        RawMaterial.objects.create(
            name='PP', model_name='HP500N/另一条', warehouse_code='RM-PP-501',
            category=RawMaterialType.objects.get(name='树脂'))
        self.assertEqual(query_count(), before)

    def test_material_grade_wildcard(self):
        texts = self._search('material', 'PA*')
        self.assertTrue(any('PA66-G30' in text for text in texts))
        self.assertFalse(any('PBT-G30' in text for text in texts))
        self.assertEqual(self._search('material', 'PA6.6'), [])
        self.assertTrue(any('PA66-G30' in text for text in self._search('material', 'PA66')))

    def test_material_import_named_grade_wildcard_ignores_non_numeric_category(self):
        texts = self._search('material_import', '', grade_name='PA*')
        self.assertTrue(any(text == 'PA66-G30' for text in texts))
        self.assertFalse(any(text == 'PBT-G30' for text in texts))
        both = self._search('material_import', '', grade_name='PA*', category_id='*')
        self.assertTrue(any(text == 'PA66-G30' for text in both))

    def test_material_project_sap_wildcard(self):
        texts = self._search('material_project', '', sap_material_code='SAP-1*')
        self.assertTrue(any('SAP-100' in text for text in texts))
        self.assertFalse(any('SAP-200' in text for text in texts))
        self.assertEqual(self._search('material_project', 'SAP-1.0'), [])

    def test_simple_name_models(self):
        self.assertEqual(self._search('material_type', '工程*'), ['工程塑料'])
        self.assertEqual(self._search('material_type', '工程.料'), [])
        self.assertEqual(self._search('scenario', '汽车*'), ['汽车内饰'])
        self.assertEqual(self._search('characteristic', '耐?'), ['耐热', '耐磨'])
        payload = self.client.get(reverse('material_api_search'), {
            'model': 'test_config', 'q': '拉伸强度',
        }).json()
        self.assertEqual(payload[0]['data_type'], 'NUMBER')
        self.assertEqual(payload[0]['options'], [])
        standards = self._search('test_config', 'ISO 52?')
        self.assertTrue(any('拉伸强度' in text for text in standards))
        self.assertFalse(any('密度' in text for text in standards))

    def test_process_project_and_research(self):
        self.assertEqual(self._search('process', '双螺杆*'), ['双螺杆A'])
        self.assertEqual(self._search('process', '双螺杆.'), [])
        self.assertEqual(self._search('commercial_project', 'PP*'), ['PP项目一'])
        codes = self._search('research_project', 'BR-00?')
        self.assertTrue(any('BR-001' in text for text in codes))
        self.assertTrue(any('BR-002' in text for text in codes))
        self.assertEqual(self._search('research_project', 'BR-00.'), [])

    def test_user_wildcard_skips_inactive(self):
        texts = self._search('user', 'pp_*')
        self.assertIn('pp_user', texts)
        self.assertNotIn('pp_inactive', texts)
        self.assertNotIn('pa_user', texts)

    def test_repository_autocomplete(self):
        self.assertEqual(self._repo('customer', 'PP*'), ['PP客户'])
        self.assertEqual(self._repo('customer', 'PP.'), [])
        oem = self._repo('oem', '主机厂?')
        self.assertEqual(sorted(oem), sorted(['主机厂甲 (甲)', '主机厂乙 (乙)']))
        sales = self._repo('salesperson', 'pp_*')
        self.assertEqual(sales, ['pp_sales'])
