"""原材料物性指标允许范围（最小值/最大值）录入行为测试。

覆盖三条链路：表单三态显隐与校验、FormSet 落库、页面渲染。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_material.models import MetricCategory, TestConfig
from app_raw_material.forms import RawMaterialPropertyForm, RawMaterialPropertyFormSet
from app_raw_material.models import RawMaterial, RawMaterialProperty, RawMaterialType
from app_user.models import ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()


class PropertyRangeTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = MetricCategory.objects.create(name="力学性能", order=1)
        cls.tc_number = TestConfig.objects.create(
            category=cls.category, name="拉伸强度", standard="ISO 527",
            unit="MPa", order=1, data_type="NUMBER")
        cls.tc_text = TestConfig.objects.create(
            category=cls.category, name="外观", standard="目视",
            order=2, data_type="TEXT")
        cls.tc_select = TestConfig.objects.create(
            category=cls.category, name="阻燃等级", standard="UL94",
            order=3, data_type="SELECT", options_config="V-0,V-1,HB")

        cls.rm_type = RawMaterialType.objects.create(name="阻燃剂", code="FR")
        cls.material = RawMaterial.objects.create(name="测试原材料", category=cls.rm_type)


class FormDisplayStateTests(PropertyRangeTestBase):
    """未绑定表单的显隐状态必须与 TestConfig.data_type 一致。"""

    def _styles(self, form):
        return {name: form.fields[name].widget.attrs.get('style', '') for name in
                ('value', 'value_text', 'value_select',
                 'min_value', 'max_value', 'min_value_text', 'max_value_text',
                 'min_value_select', 'max_value_select')}

    def test_number_type_shows_numeric_inputs_only(self):
        prop = RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number, value=10)
        s = self._styles(RawMaterialPropertyForm(instance=prop))
        self.assertNotIn('none', s['value'])
        self.assertNotIn('none', s['min_value'])
        self.assertNotIn('none', s['max_value'])
        for hidden in ('value_text', 'min_value_text', 'max_value_text',
                       'value_select', 'min_value_select', 'max_value_select'):
            self.assertIn('none', s[hidden], hidden)

    def test_text_type_shows_text_inputs_only(self):
        prop = RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_text, value_text="合格")
        s = self._styles(RawMaterialPropertyForm(instance=prop))
        self.assertNotIn('none', s['value_text'])
        self.assertNotIn('none', s['min_value_text'])
        self.assertNotIn('none', s['max_value_text'])
        for hidden in ('value', 'min_value', 'max_value',
                       'value_select', 'min_value_select', 'max_value_select'):
            self.assertIn('none', s[hidden], hidden)

    def test_select_type_shows_select_inputs_only(self):
        prop = RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_select, value_text="V-0")
        form = RawMaterialPropertyForm(instance=prop)
        s = self._styles(form)
        self.assertNotIn('none', s['value_select'])
        self.assertNotIn('none', s['min_value_select'])
        self.assertNotIn('none', s['max_value_select'])
        for hidden in ('value', 'min_value', 'max_value',
                       'value_text', 'min_value_text', 'max_value_text'):
            self.assertIn('none', s[hidden], hidden)
        # 三个下拉都要有选项
        expected = [('V-0', 'V-0'), ('V-1', 'V-1'), ('HB', 'HB')]
        self.assertEqual(list(form.fields['min_value_select'].choices), expected)
        self.assertEqual(list(form.fields['max_value_select'].choices), expected)


class FormValidationTests(PropertyRangeTestBase):
    def test_number_min_greater_than_max_rejected(self):
        form = RawMaterialPropertyForm(data={
            'test_config': self.tc_number.pk, 'value': '10',
            'min_value': '20', 'max_value': '5', 'value_text': '',
            'min_value_text': '', 'max_value_text': '', 'remark': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn("最小值不能大于最大值", form.non_field_errors())

    def test_number_range_saved(self):
        form = RawMaterialPropertyForm(data={
            'test_config': self.tc_number.pk, 'value': '10',
            'min_value': '5', 'max_value': '15', 'value_text': '',
            'min_value_text': '', 'max_value_text': '', 'remark': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        prop = form.save(commit=False)
        self.assertEqual(prop.min_value, 5)
        self.assertEqual(prop.max_value, 15)

    def test_select_range_written_to_text_fields(self):
        form = RawMaterialPropertyForm(data={
            'test_config': self.tc_select.pk, 'value_select': 'V-0',
            'min_value_select': 'V-0', 'max_value_select': 'V-1',
            'value': '', 'value_text': '', 'min_value_text': '',
            'max_value_text': '', 'remark': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        cleaned = form.cleaned_data
        self.assertEqual(cleaned['value_text'], 'V-0')
        self.assertEqual(cleaned['min_value_text'], 'V-0')
        self.assertEqual(cleaned['max_value_text'], 'V-1')


class FormSetPersistenceTests(PropertyRangeTestBase):
    def test_formset_saves_range(self):
        data = {
            'properties-TOTAL_FORMS': '1',
            'properties-INITIAL_FORMS': '0',
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
            'properties-0-test_config': str(self.tc_number.pk),
            'properties-0-value': '10',
            'properties-0-min_value': '5',
            'properties-0-max_value': '15',
            'properties-0-id': '',
            'properties-0-value_text': '',
            'properties-0-min_value_text': '',
            'properties-0-max_value_text': '',
            'properties-0-test_date': '',
            'properties-0-remark': '',
        }
        formset = RawMaterialPropertyFormSet(data, instance=self.material)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        prop = self.material.properties.get(test_config=self.tc_number)
        self.assertEqual(prop.min_value, 5)
        self.assertEqual(prop.max_value, 15)

    def test_extra_is_per_instance_not_leaked(self):
        """构造两次 FormSet，extra 设置不得互相污染（回归：曾直接改类属性）。"""
        first = RawMaterialPropertyFormSet(queryset=RawMaterialProperty.objects.none())
        first.extra = 4
        second = RawMaterialPropertyFormSet(queryset=RawMaterialProperty.objects.none())
        second.extra = 1
        self.assertEqual(len(first.forms), 4)
        self.assertEqual(len(second.forms), 1)


class PageRenderTests(PropertyRangeTestBase):
    """录入页/详情页必须能真实渲染出新列，且不丢 test_date。"""

    def setUp(self):
        # RBAC 基础数据 —— 与 test_permissions.py 保持一致的 L1 角色组配置
        role = UserRole.objects.create(code='ENGINEER', name='研发工程师')
        group = RoleGroup.objects.create(code='RND_Center_Engineer_Team', name='研发工程师团队')
        group.roles.add(role)
        cfg = ModuleAccessConfig.objects.create(
            module_code='raw_material', module_name='原材料/供应商',
            enforce_dept_isolation=False, enforce_group_isolation=False)
        cfg.role_groups.add(group)
        IdentityService.invalidate_cache()

        self.user = User.objects.create_user(
            username='editor', email='editor@test.dev', password='x')
        self.user.user_type = role
        self.user.save()
        self.user.user_permissions.add(*Permission.objects.filter(
            codename__in=['view_rawmaterial', 'add_rawmaterial', 'change_rawmaterial'],
            content_type__app_label='app_raw_material'))
        self.client.force_login(self.user)

    def test_create_page_renders_range_columns(self):
        resp = self.client.get(reverse('raw_material_add'))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('最小值', html)
        self.assertIn('最大值', html)
        self.assertIn('value-min', html)
        self.assertIn('value-max-text', html)
        self.assertIn('value-min-select', html)
        # 默认 4 行空表单
        self.assertEqual(html.count('name="properties-0-test_config"'), 1)

    def test_update_page_renders_saved_range(self):
        RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number,
            value=10, min_value=5, max_value=15)
        resp = self.client.get(reverse('raw_material_edit', kwargs={'pk': self.material.pk}))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('value-min', html)

    def test_detail_page_renders_range_and_test_date(self):
        RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number,
            value=10, min_value=5, max_value=15)
        prop_text = RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_text,
            value_text="合格", min_value_text="合格", max_value_text="优")
        prop_select = RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_select,
            value_text="V-0", min_value_text="V-0", max_value_text="V-1")

        resp = self.client.get(reverse('raw_material_detail', kwargs={'pk': self.material.pk}))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('标准范围', html)
        self.assertIn('[5.00 ~ 15.00]', html)
        self.assertIn('[合格 ~ 优]', html)
        self.assertIn('[V-0 ~ V-1]', html)
        # test_date 列仍在（区别于成品 MaterialDataPoint）
        self.assertIn('测试日期', html)
        self.assertIn(prop_text.value_text, html) and self.assertIn(prop_select.value_text, html)

    def test_detail_page_renders_single_sided_range(self):
        RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number, value=10, min_value=5)
        resp = self.client.get(reverse('raw_material_detail', kwargs={'pk': self.material.pk}))
        self.assertIn('[≥ 5.00]', resp.content.decode())

    def _property_row(self, *, min_value='', max_value='', value='10', prefix='properties-0'):
        return {
            f'{prefix}-test_config': str(self.tc_number.pk),
            f'{prefix}-value': value,
            f'{prefix}-min_value': min_value,
            f'{prefix}-max_value': max_value,
            f'{prefix}-id': '',
            f'{prefix}-value_text': '',
            f'{prefix}-min_value_text': '',
            f'{prefix}-max_value_text': '',
            f'{prefix}-test_date': '',
            f'{prefix}-remark': '',
        }

    def _create_payload(self, **row):
        return {
            'name': '待校验原材料', 'category': self.rm_type.pk, 'model_name': '',
            'warehouse_code': '', 'purchase_date': '', 'usage_method': '', 'supplier': '',
            'properties-TOTAL_FORMS': '1', 'properties-INITIAL_FORMS': '0',
            'properties-MIN_NUM_FORMS': '0', 'properties-MAX_NUM_FORMS': '1000',
            **self._property_row(**row),
        }

    def test_formset_error_rolls_back_create(self):
        """回归：formset 校验失败时主表不得落库（原先 atomic 块内直接 return 会提交）。"""
        resp = self.client.post(reverse('raw_material_add'),
                                self._create_payload(min_value='20', max_value='5'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(RawMaterial.objects.filter(name='待校验原材料').exists())

    def test_formset_error_is_visible(self):
        """回归：min > max 的报错必须渲染到页面上（原先 formset 错误无处显示）。"""
        resp = self.client.post(reverse('raw_material_add'),
                                self._create_payload(min_value='20', max_value='5'))
        html = resp.content.decode()
        self.assertIn('最小值不能大于最大值', html)
        self.assertIn('table-danger', html)

    def test_formset_error_rolls_back_edit(self):
        RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number,
            value=10, min_value=5, max_value=15)
        payload = {
            'name': '改名后不应生效', 'category': self.rm_type.pk, 'model_name': '',
            'warehouse_code': '', 'purchase_date': '', 'usage_method': '', 'supplier': '',
            'properties-TOTAL_FORMS': '1', 'properties-INITIAL_FORMS': '1',
            'properties-MIN_NUM_FORMS': '0', 'properties-MAX_NUM_FORMS': '1000',
        }
        prop = self.material.properties.get(test_config=self.tc_number)
        payload.update(self._property_row(min_value='20', max_value='5'))
        payload['properties-0-id'] = str(prop.pk)

        resp = self.client.post(
            reverse('raw_material_edit', kwargs={'pk': self.material.pk}), payload)
        self.assertEqual(resp.status_code, 200)
        self.material.refresh_from_db()
        self.assertEqual(self.material.name, '测试原材料')
        prop.refresh_from_db()
        self.assertEqual(prop.min_value, 5)

    def test_formset_error_rolls_back_duplicate(self):
        RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number,
            value=10, min_value=5, max_value=15)
        before = RawMaterial.objects.count()
        resp = self.client.post(
            reverse('raw_material_duplicate', kwargs={'pk': self.material.pk}),
            self._create_payload(min_value='20', max_value='5'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(RawMaterial.objects.count(), before)

    def test_valid_create_still_saves_range(self):
        """对照组：合法提交必须正常落库（确认回滚没有误伤成功路径）。"""
        resp = self.client.post(reverse('raw_material_add'),
                                self._create_payload(min_value='5', max_value='15'))
        self.assertEqual(resp.status_code, 302)
        created = RawMaterial.objects.get(name='待校验原材料')
        prop = created.properties.get(test_config=self.tc_number)
        self.assertEqual(prop.min_value, 5)
        self.assertEqual(prop.max_value, 15)

    def test_duplicate_page_prefills_range(self):
        RawMaterialProperty.objects.create(
            raw_material=self.material, test_config=self.tc_number,
            value=10, min_value=5, max_value=15)
        resp = self.client.get(reverse('raw_material_duplicate', kwargs={'pk': self.material.pk}))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        # DecimalField(decimal_places=3) 渲染为 5.000 / 15.000
        self.assertRegex(html, r'name="properties-0-min_value" value="5\.000"')
        self.assertRegex(html, r'name="properties-0-max_value" value="15\.000"')
