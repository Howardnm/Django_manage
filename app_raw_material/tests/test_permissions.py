"""app_raw_material 权限回归测试。

验证原材料模块的 L1~L3 权限控制（原材料/供应商/类型为 SAP 同步的共享参考数据，
无创建人归属概念，L4/L5 隔离关闭）：

- L1 角色组：仅 `RND_Center_Engineer_Team` / `RND_Center_management_team`
  两个角色组的成员可访问；组外用户即使持有 Django 权限码也被拒绝。
- L2 等级：min_level=1（本测试用户默认等级 1，均在门槛上）。
- L3 权限码：view_* 管查看、add_* 管新增、change_* 管编辑。
- 编辑权限（回归重点）：无归属数据不被默认「仅所有者可编辑」逻辑误拒，
  持有 change_* 权限的角色组成员可正常编辑（RawMaterialAccessMixin
  已覆盖 check_edit_permission 放行，见 app_raw_material/mixins.py）。

覆盖视图：原材料 list/detail/add/edit/duplicate、
类型 list/add/edit、供应商 list/detail/add/edit。
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_user.models import ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

from app_raw_material.models import RawMaterial, RawMaterialType, Supplier

User = get_user_model()


def _grant(user, *codenames):
    """为测试用户授予 app_raw_material 下的 Django 权限码（L3）。"""
    perms = Permission.objects.filter(
        codename__in=codenames, content_type__app_label='app_raw_material')
    user.user_permissions.add(*perms)


class RawMaterialAccessTests(TestCase):
    """围绕原材料/供应商/类型三组视图的 L1~L3 权限回归。"""

    def setUp(self):
        # ── RBAC 基础数据（与 DB 中 raw_material 模块配置一致）──
        self.engineer = UserRole.objects.create(code='ENGINEER', name='研发工程师')
        self.manager = UserRole.objects.create(code='RND_MANAGER', name='研发中心管理')
        self.sales = UserRole.objects.create(code='SALES', name='销售')

        eng_group = RoleGroup.objects.create(
            code='RND_Center_Engineer_Team', name='研发中心工程师团队')
        eng_group.roles.add(self.engineer)
        mgr_group = RoleGroup.objects.create(
            code='RND_Center_management_team', name='研发中心管理团队')
        mgr_group.roles.add(self.manager)

        cfg = ModuleAccessConfig.objects.create(
            module_code='raw_material', module_name='原材料/供应商',
            enforce_dept_isolation=False, enforce_group_isolation=False,
        )
        cfg.role_groups.add(eng_group, mgr_group)
        IdentityService.invalidate_cache()

        # ── 业务测试数据 ──
        self.category = RawMaterialType.objects.create(name='树脂')
        self.supplier = Supplier.objects.create(name='测试供应商')
        self.material = RawMaterial.objects.create(name='PA66', category=self.category)

        # ── 测试用户 ──
        self.viewer = self._make_user('viewer', self.engineer,
            'view_rawmaterial', 'view_rawmaterialtype', 'view_supplier')
        self.editor = self._make_user('editor', self.engineer,
            'view_rawmaterial', 'add_rawmaterial', 'change_rawmaterial',
            'view_rawmaterialtype', 'add_rawmaterialtype', 'change_rawmaterialtype',
            'view_supplier', 'add_supplier', 'change_supplier')
        self.noperm = self._make_user('noperm', self.engineer)  # 组内、无任何 L3 权限码
        self.outsider = self._make_user('outsider', self.sales,
            'view_rawmaterial', 'change_rawmaterial')  # 组外、纵有权限码也拒绝
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')

    def _make_user(self, username, role, *perms):
        user = User.objects.create_user(
            username=username, email=f'{username}@test.dev', password='x')
        user.user_type = role
        user.save()
        if perms:
            _grant(user, *perms)
        return user

    def assert_denied(self, response, url_name='permission_denied'):
        """非 AJAX 请求被拒 → 302 重定向到 /permission-denied/。"""
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse(url_name), response.url)

    # ───────────────────────── 匿名 / 超管 ─────────────────────────

    def test_anonymous_redirects_to_login(self):
        response = self.client.get(reverse('raw_material_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_superuser_access_everything(self):
        self.client.force_login(self.admin)
        for url_name in ('raw_material_list', 'raw_material_add',
                         'raw_type_list', 'raw_type_add',
                         'raw_supplier_list', 'raw_supplier_add'):
            self.assertEqual(self.client.get(reverse(url_name)).status_code, 200,
                             f'{url_name} 超管应可访问')

    # ───────────────────────── 查看权限（view_*）─────────────────────────

    def test_viewer_can_read(self):
        """有 view 权限的角色组成员可访问全部列表/详情页。"""
        self.client.force_login(self.viewer)
        self.assertEqual(self.client.get(reverse('raw_material_list')).status_code, 200)
        self.assertEqual(self.client.get(
            reverse('raw_material_detail', args=[self.material.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('raw_type_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('raw_supplier_list')).status_code, 200)
        self.assertEqual(self.client.get(
            reverse('raw_supplier_detail', args=[self.supplier.pk])).status_code, 200)

    def test_viewer_cannot_write(self):
        """只有 view 权限，无 add/change → 新增/编辑/复制页均被拒。"""
        self.client.force_login(self.viewer)
        simple = [
            reverse('raw_material_add'),
            reverse('raw_material_edit', args=[self.material.pk]),
            reverse('raw_material_duplicate', args=[self.material.pk]),
            reverse('raw_type_add'),
            reverse('raw_type_edit', args=[self.category.pk]),
            reverse('raw_supplier_add'),
            reverse('raw_supplier_edit', args=[self.supplier.pk]),
        ]
        for url in simple:
            self.assert_denied(self.client.get(url))

    # ───────────────────────── 编辑权限（change_*）─────────────────────────

    def test_editor_can_write_get_pages(self):
        """有 add/change 权限的角色组成员可访问全部新增/编辑/复制页。"""
        self.client.force_login(self.editor)
        simple = [
            reverse('raw_material_add'),
            reverse('raw_material_edit', args=[self.material.pk]),
            reverse('raw_material_duplicate', args=[self.material.pk]),
            reverse('raw_type_add'),
            reverse('raw_type_edit', args=[self.category.pk]),
            reverse('raw_supplier_add'),
            reverse('raw_supplier_edit', args=[self.supplier.pk]),
        ]
        for url in simple:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_editor_can_post_edit_material(self):
        """回归重点：无归属的原材料，有 change 权限者可真正保存（不被误拒）。"""
        self.client.force_login(self.editor)
        data = {
            'name': 'PA66 改性',
            'category': self.category.pk,
            'properties-TOTAL_FORMS': '0',
            'properties-INITIAL_FORMS': '0',
            'properties-MIN_NUM_FORMS': '0',
            'properties-MAX_NUM_FORMS': '1000',
        }
        response = self.client.post(
            reverse('raw_material_edit', args=[self.material.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual(self.material.name, 'PA66 改性')

    def test_editor_can_post_edit_type(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('raw_type_edit', args=[self.category.pk]),
            {'name': '树脂(改)', 'order': 0})
        self.assertEqual(response.status_code, 302)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, '树脂(改)')

    def test_editor_can_post_edit_supplier(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse('raw_supplier_edit', args=[self.supplier.pk]), {'name': '测试供应商(改)'})
        self.assertEqual(response.status_code, 302)
        self.supplier.refresh_from_db()
        self.assertEqual(self.supplier.name, '测试供应商(改)')

    # ───────────────────────── L1 组外拒绝 ────────────────────────

    def test_outsider_denied_even_with_perms(self):
        """非研发中心角色组用户，即使持有 Django 权限码也全部拒绝（L1 闸门）。"""
        self.client.force_login(self.outsider)
        urls = [
            reverse('raw_material_list'),
            reverse('raw_material_detail', args=[self.material.pk]),
            reverse('raw_material_edit', args=[self.material.pk]),
            reverse('raw_type_list'),
            reverse('raw_supplier_list'),
        ]
        for url in urls:
            self.assert_denied(self.client.get(url))

    # ───────────────────────── L3 组内无权限拒绝 ────────────────────────

    def test_noperm_member_denied(self):
        """组内但没有 view 权限码 → 列表页也被拒（L3 仍生效）。"""
        self.client.force_login(self.noperm)
        self.assert_denied(self.client.get(reverse('raw_material_list')))
        self.assert_denied(self.client.get(reverse('raw_type_list')))
        self.assert_denied(self.client.get(reverse('raw_supplier_list')))