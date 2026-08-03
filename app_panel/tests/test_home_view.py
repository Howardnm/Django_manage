"""首页权限测试：验证首页走独立 home 模块，与看板工作台（panel）权限解耦。

覆盖场景：
- 有 home 角色组的用户可访问首页
- 无 home 角色组的用户被转 403
- 未登录被转登录页
- 超管不受 home 配置限制
- 有 home 无 panel 的用户：首页 200、无"进入个人工作台"按钮、个人工作台被转 403
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_user.models import ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()


class HomeAccessTests(TestCase):
    def setUp(self):
        # ── RBAC 基础数据 ──
        rnd = UserRole.objects.create(code='RND', name='研发', is_internal=True)
        sales = UserRole.objects.create(code='SALES', name='销售', is_internal=True)

        rnd_group = RoleGroup.objects.create(code='RND_ONLY', name='研发组')
        rnd_group.roles.add(rnd)
        sales_group = RoleGroup.objects.create(code='SALES_TEAM', name='销售组')
        sales_group.roles.add(sales)

        # home 模块：RND + SALES 均可访问首页
        home_cfg = ModuleAccessConfig.objects.create(
            module_code='home', module_name='系统首页'
        )
        home_cfg.role_groups.add(rnd_group, sales_group)

        # panel 模块：仅 RND 可访问看板工作台
        panel_cfg = ModuleAccessConfig.objects.create(
            module_code='panel', module_name='看板工作台'
        )
        panel_cfg.role_groups.add(rnd_group)

        # 清空 IdentityService 缓存，避免测试间脏读
        IdentityService.invalidate_cache()

        # ── 用户 ──
        self.rnd_user = User.objects.create_user(username='engineer', password='test')
        self.rnd_user.user_type = rnd
        self.rnd_user.save()

        self.sales_user = User.objects.create_user(username='sales', password='test')
        self.sales_user.user_type = sales
        self.sales_user.save()

    def test_anonymous_redirects_to_login(self):
        """未登录访问首页 → 重定向登录页"""
        response = self.client.get(reverse('panel_home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_home_accessible_with_home_role(self):
        """有 home 角色组（RND）的用户可访问首页"""
        self.client.force_login(self.rnd_user)
        response = self.client.get(reverse('panel_home'))
        self.assertEqual(response.status_code, 200)

    def test_home_denied_without_home_role(self):
        """无 home 角色组的用户访问首页 → 转 403 页"""
        self.client.force_login(self.sales_user)
        # 先把 SALES 从 home 角色组移除，模拟"无 home 权限"
        home_cfg = ModuleAccessConfig.objects.get(module_code='home')
        home_cfg.role_groups.clear()
        home_cfg.role_groups.add(RoleGroup.objects.get(code='RND_ONLY'))
        IdentityService.invalidate_cache()

        response = self.client.get(reverse('panel_home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('permission_denied'), response.url)

    def test_superuser_bypasses_home_config(self):
        """超管不受 home 配置限制，直接访问首页"""
        admin = User.objects.create_superuser(username='admin', password='test')
        self.client.force_login(admin)
        response = self.client.get(reverse('panel_home'))
        self.assertEqual(response.status_code, 200)

    def test_home_without_panel_hides_workspace_button(self):
        """有 home 无 panel 的用户：首页 200，has_panel_access=False，个人工作台被转 403"""
        self.client.force_login(self.sales_user)  # SALES 在 home 组、不在 panel 组
        response = self.client.get(reverse('panel_home'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['has_panel_access'])

        # 直接访问个人工作台 → 403 页
        response = self.client.get(reverse('personal_workspace'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('permission_denied'), response.url)

    def test_home_with_panel_shows_workspace_button(self):
        """有 home + panel 的用户：has_panel_access=True，个人工作台可访问"""
        self.client.force_login(self.rnd_user)  # RND 在 home + panel 组
        response = self.client.get(reverse('panel_home'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['has_panel_access'])