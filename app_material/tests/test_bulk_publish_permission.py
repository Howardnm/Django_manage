"""材料批量发布/下架的对象级权限。

编辑权限仍是「仅创建人 / 超管」。发布单独放宽：
同启用工作组，或 material.management 角色组里的管理层身份。
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_material.models import MaterialLibrary, MaterialType
from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole, WorkGroup
from app_user.services.identity_service import IdentityService

User = get_user_model()


class MaterialBulkPublishPermissionTests(TestCase):
    def setUp(self):
        self.material_type = MaterialType.objects.create(name='工程塑料')
        self.dept = Department.objects.create(name='研发中心')
        self.alpha = WorkGroup.objects.create(name='配方组', department=self.dept)
        self.beta = WorkGroup.objects.create(name='应用组', department=self.dept)
        self.retired = WorkGroup.objects.create(
            name='已解散组', department=self.dept, is_active=False)

        engineer = UserRole.objects.create(code='ENGINEER', name='研发工程师')
        manager_role = UserRole.objects.create(code='RD_MANAGER', name='研发经理')
        eng_group = RoleGroup.objects.create(
            code='RND_Center_Engineer_Team', name='研发工程师团队')
        eng_group.roles.add(engineer)
        mgr_group = RoleGroup.objects.create(
            code='RND_Center_management_team', name='研发中心_管理层组')
        mgr_group.roles.add(manager_role)

        material_cfg = ModuleAccessConfig.objects.create(
            module_code='material', module_name='材料成品库',
            enforce_dept_isolation=False, enforce_group_isolation=False)
        material_cfg.role_groups.add(eng_group, mgr_group)
        self.mgmt_cfg = ModuleAccessConfig.objects.create(
            module_code='material.management', module_name='材料成品库-管理层',
            enforce_dept_isolation=False, enforce_group_isolation=False)
        self.mgmt_cfg.role_groups.add(mgr_group)
        IdentityService.invalidate_cache()

        change_perm = Permission.objects.filter(
            codename='change_materiallibrary', content_type__app_label='app_material')

        def make_user(username, role, *groups):
            user = User.objects.create_user(
                username=username, email=f'{username}@test.dev', password='x')
            user.user_type = role
            user.department = self.dept
            user.save()
            user.user_permissions.add(*change_perm)
            for group in groups:
                group.members.add(user)
            return user

        self.creator = make_user('creator', engineer, self.alpha, self.retired)
        self.teammate = make_user('teammate', engineer, self.alpha)
        self.outsider = make_user('outsider', engineer, self.beta)
        self.retired_peer = make_user('retired_peer', engineer, self.retired)
        self.manager = make_user('manager', manager_role, self.beta)
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.dev', password='x')

        self.own = self._grade('OWN-GRADE', self.creator, 'SAP-OWN')

    def _grade(self, name, creator, sap):
        return MaterialLibrary.objects.create(
            grade_name=name, sap_material_code=sap,
            category=self.material_type, creator=creator)

    def _post(self, user, materials, action='publish'):
        self.client.force_login(user)
        return self.client.post(
            reverse('material_bulk_publish'),
            data=json.dumps({
                'ids': [m.pk for m in materials],
                'action': action,
            }),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def _assert_published(self, user, material):
        resp = self._post(user, [material])
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['status'], 'success')
        material.refresh_from_db()
        self.assertTrue(material.is_published)

    def _assert_denied(self, user, material):
        resp = self._post(user, [material])
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertIn(material.grade_name, resp.json()['message'])
        material.refresh_from_db()
        self.assertFalse(material.is_published)
        return resp

    def test_creator_can_publish(self):
        self._assert_published(self.creator, self.own)

    def test_active_work_group_peer_can_publish_and_unpublish(self):
        self._assert_published(self.teammate, self.own)
        resp = self._post(self.teammate, [self.own], action='unpublish')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.own.refresh_from_db()
        self.assertFalse(self.own.is_published)

    def test_manager_in_another_work_group_can_publish(self):
        self._assert_published(self.manager, self.own)

    def test_superuser_can_publish(self):
        self._assert_published(self.admin, self.own)

    def test_other_work_group_engineer_is_denied(self):
        self._assert_denied(self.outsider, self.own)

    def test_inactive_work_group_overlap_does_not_count(self):
        self._assert_denied(self.retired_peer, self.own)

    def test_unconfigured_management_module_denies_cross_group_publish(self):
        self.mgmt_cfg.role_groups.clear()
        IdentityService.invalidate_cache()
        self._assert_denied(self.manager, self.own)

    def test_null_creator_is_not_opened_by_work_group_but_manager_can(self):
        orphan = self._grade('ORPHAN-GRADE', None, 'SAP-ORPHAN')
        self._assert_denied(self.teammate, orphan)
        self._assert_published(self.manager, orphan)

    def test_mixed_batch_updates_nothing(self):
        other = self._grade('OTHER-GRADE', self.outsider, 'SAP-OTHER')
        resp = self._post(self.teammate, [self.own, other])
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertIn(other.grade_name, resp.json()['message'])
        self.own.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(self.own.is_published)
        self.assertFalse(other.is_published)

    def test_work_group_peer_still_cannot_edit(self):
        self.client.force_login(self.teammate)
        resp = self.client.post(
            reverse('material_edit', kwargs={'pk': self.own.pk}),
            {
                'grade_name': '改名不应生效',
                'manufacturer': '',
                'sap_material_code': self.own.sap_material_code,
                'category': self.material_type.pk,
                'flammability': '',
                'material_color_name': '',
                'pantone_code': '',
                'rgb_value': '',
                'description': '不应保存',
                'properties-TOTAL_FORMS': '0',
                'properties-INITIAL_FORMS': '0',
                'properties-MIN_NUM_FORMS': '0',
                'properties-MAX_NUM_FORMS': '1000',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertIn('仅数据所有者', resp.json()['message'])
        self.own.refresh_from_db()
        self.assertEqual(self.own.grade_name, 'OWN-GRADE')
        self.assertEqual(self.own.description, '')
