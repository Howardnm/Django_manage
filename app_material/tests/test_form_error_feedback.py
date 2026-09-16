"""材料录入页表单/表单集错误的用户可见性回归。

背景（回归重点）：物性明细是 inline formset，`MaterialDataPointForm.clean()` 抛出的
「最小值不能大于最大值」落在子表单的 `non_field_errors` 上。录入模板只逐行渲染
value / test_config 的字段错误，不渲染 `__all__`，因此这类错误必须经 messages
回显，否则表单静默弹回、用户看不到任何提示。

同时锁定事务语义：主表不得在 formset 校验失败时被提交。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_material.mixins import MaterialFormErrorMixin
from app_material.models import (MaterialDataPoint, MaterialLibrary, MaterialType,
                                 MetricCategory, TestConfig)
from app_user.models import ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()

MSG = '最小值不能大于最大值'


class MaterialFormErrorFeedbackBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = MetricCategory.objects.create(name='力学性能', order=1)
        cls.test_config = TestConfig.objects.create(
            category=category, name='拉伸强度', standard='ISO 527',
            unit='MPa', order=1, data_type='NUMBER')
        cls.material_type = MaterialType.objects.create(name='工程塑料')

    def setUp(self):
        role = UserRole.objects.create(code='ENGINEER', name='研发工程师')
        group = RoleGroup.objects.create(code='RND_Center_Engineer_Team', name='研发工程师团队')
        group.roles.add(role)
        cfg = ModuleAccessConfig.objects.create(
            module_code='material', module_name='材料成品库',
            enforce_dept_isolation=False, enforce_group_isolation=False)
        cfg.role_groups.add(group)
        IdentityService.invalidate_cache()

        self.user = User.objects.create_user(
            username='editor', email='editor@test.dev', password='x')
        self.user.user_type = role
        self.user.save()
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_materiallibrary', 'add_materiallibrary',
                          'change_materiallibrary'],
            content_type__app_label='app_material'))
        self.client.force_login(self.user)

    def _property_row(self, *, test_config=None, min_value, max_value, pk='', prefix='properties-0'):
        return {
            f'{prefix}-test_config': str((test_config or self.test_config).pk),
            f'{prefix}-value': '10',
            f'{prefix}-min_value': min_value,
            f'{prefix}-max_value': max_value,
            f'{prefix}-id': pk,
            f'{prefix}-value_text': '',
            f'{prefix}-min_value_text': '',
            f'{prefix}-max_value_text': '',
            f'{prefix}-remark': '',
        }

    def _payload(self, *, initial_forms='0', grade_name='FEEDBACK-TEST-001', **row_kwargs):
        return {
            'grade_name': grade_name,
            'manufacturer': '', 'sap_material_code': 'A01000', 'category': self.material_type.pk,
            'flammability': '', 'material_color_name': '', 'pantone_code': '', 'rgb_value': '',
            'description': '', 'is_published': '',
            'properties-TOTAL_FORMS': '1',
            'properties-INITIAL_FORMS': initial_forms,
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
            **self._property_row(**row_kwargs),
        }


class CreatePageErrorFeedbackTests(MaterialFormErrorFeedbackBase):
    def test_formset_error_is_reported(self):
        """回归：新增页 formset 校验失败原先静默弹回，用户看不到「最小值不能大于最大值」。"""
        resp = self.client.post(reverse('material_add'), self._payload(min_value='20', max_value='5'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(MSG, resp.content.decode())

    def test_formset_error_does_not_leak_master_row(self):
        self.client.post(reverse('material_add'), self._payload(min_value='20', max_value='5'))
        self.assertFalse(MaterialLibrary.objects.filter(grade_name='FEEDBACK-TEST-001').exists())

    def test_main_form_error_is_reported(self):
        """回归：主表单自身校验失败原先也无任何提示。"""
        payload = self._payload(min_value='5', max_value='15')
        payload['grade_name'] = ''  # 牌号必填
        resp = self.client.post(reverse('material_add'), payload)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('保存失败，请修正以下问题', html)
        self.assertIn('材料牌号', html)

    def test_valid_create_still_saves(self):
        """对照组：合法提交必须正常落库（确认新增的错误回显没有误伤成功路径）。"""
        resp = self.client.post(reverse('material_add'), self._payload(min_value='5', max_value='15'))
        self.assertEqual(resp.status_code, 302)
        material = MaterialLibrary.objects.get(grade_name='FEEDBACK-TEST-001')
        point = material.properties.get(test_config=self.test_config)
        self.assertEqual(point.min_value, 5)
        self.assertEqual(point.max_value, 15)
        self.assertEqual(material.creator, self.user)


class EditPageErrorFeedbackTests(MaterialFormErrorFeedbackBase):
    def setUp(self):
        super().setUp()
        self.material = MaterialLibrary.objects.create(
            grade_name='EDIT-FEEDBACK', sap_material_code='A02000',
            category=self.material_type, creator=self.user)
        self.point = MaterialDataPoint.objects.create(
            material=self.material, test_config=self.test_config,
            value=10, min_value=5, max_value=15)

    def test_formset_error_is_reported(self):
        resp = self.client.post(
            reverse('material_edit', kwargs={'pk': self.material.pk}),
            self._payload(initial_forms='1', grade_name='EDIT-FEEDBACK',
                          min_value='20', max_value='5', pk=str(self.point.pk)))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(MSG, resp.content.decode())

    def test_formset_error_rolls_back(self):
        self.client.post(
            reverse('material_edit', kwargs={'pk': self.material.pk}),
            self._payload(initial_forms='1', grade_name='改名不应生效',
                          min_value='20', max_value='5', pk=str(self.point.pk)))
        self.material.refresh_from_db()
        self.point.refresh_from_db()
        self.assertEqual(self.material.grade_name, 'EDIT-FEEDBACK')
        self.assertEqual(self.point.min_value, 5)


class BuildErrorMessageTests(TestCase):
    """直接锁定错误汇总文案的结构，包括 formset 不带字段名时的行号定位。"""

    def test_formset_non_field_error_reports_row_number(self):
        from app_material.forms import MaterialDataFormSet
        category = MetricCategory.objects.create(name='力学', order=1)
        tc = TestConfig.objects.create(category=category, name='拉伸', standard='ISO 527',
                                       order=1, data_type='NUMBER')
        formset = MaterialDataFormSet({
            'properties-TOTAL_FORMS': '1', 'properties-INITIAL_FORMS': '0',
            'properties-MIN_NUM_FORMS': '0', 'properties-MAX_NUM_FORMS': '1000',
            'properties-0-test_config': str(tc.pk), 'properties-0-value': '10',
            'properties-0-min_value': '20', 'properties-0-max_value': '5',
            'properties-0-id': '', 'properties-0-value_text': '',
            'properties-0-min_value_text': '', 'properties-0-max_value_text': '',
            'properties-0-remark': '',
        })
        self.assertFalse(formset.is_valid())
        from app_material.forms import MaterialForm
        message = MaterialFormErrorMixin()._build_error_message(MaterialForm(), formset)
        self.assertIn('第1行', message)
        self.assertIn(MSG, message)
