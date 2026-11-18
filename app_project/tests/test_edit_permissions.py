"""项目详情三个写入口：非所有者提交时给出 message，且不改数据。

- 阶段节点（更新 / 申报异常 / 客户意见）是 HTMX，拒绝后 204 + HX-Refresh，
  刷新详情页能看到「仅数据所有者可编辑此记录。」
- 项目信息、项目档案是整页表单，拒绝后留在表单页并渲染同一条 message。
- 档案编辑人是项目负责人或业务员，不是「能打开页面的同部门同事」。
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from app_project.models import Project
from app_user.models import Department, ModuleAccessConfig, RoleGroup, UserRole
from app_user.services.identity_service import IdentityService

User = get_user_model()


def _grant(user, app_label, *codenames):
    perms = Permission.objects.filter(
        codename__in=codenames, content_type__app_label=app_label,
    )
    user.user_permissions.add(*perms)


class EditPermissionMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role = UserRole.objects.create(code='EDIT_PERM_RD', name='研发')
        group = RoleGroup.objects.create(code='EDIT_PERM_RND', name='研发组')
        group.roles.add(role)
        for code, name in (('project', '项目'), ('repository', '档案')):
            cfg = ModuleAccessConfig.objects.create(
                module_code=code,
                module_name=name,
                min_level=1,
                enforce_dept_isolation=True,
                enforce_group_isolation=False,
            )
            cfg.role_groups.add(group)
        IdentityService.invalidate_cache('edit-perm-setup')

        cls.dept = Department.objects.create(name='编辑权限-部门')
        cls.other_dept = Department.objects.create(name='编辑权限-外部门')

        def make(username, department):
            user = User.objects.create_user(
                username=username, email=f'{username}@edit-perm.test', password='x',
                department=department,
            )
            user.user_type = role
            user.save(update_fields=['user_type'])
            _grant(user, 'app_project', 'view_project', 'change_project')
            _grant(user, 'app_repository', 'view_projectrepository', 'change_projectrepository')
            return user

        cls.manager = make('edit_mgr', cls.dept)
        cls.member = make('edit_member', cls.other_dept)
        cls.colleague = make('edit_colleague', cls.dept)
        cls.salesperson = make('edit_sales', cls.other_dept)

        cls.project = Project.objects.create(
            code='EDIT-PERM-1', name='权限项目', manager=cls.manager,
        )
        cls.project.members.create(user=cls.member)
        cls.repo = cls.project.repository
        cls.repo.salesperson = cls.salesperson
        cls.repo.product_name = '原产品'
        cls.repo.save(update_fields=['salesperson', 'product_name'])
        cls.node = cls.project.nodes.get(stage='INIT')

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        IdentityService.invalidate_cache('edit-perm-teardown')

    def test_member_node_update_shows_message_and_keeps_data(self):
        self.client.force_login(self.member)
        before = self.node.remark
        resp = self.client.post(
            reverse('node_update', args=[self.node.pk]),
            {'status': 'PAUSED', 'remark': '成员乱改'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers.get('HX-Refresh'), 'true')
        self.node.refresh_from_db()
        self.assertEqual(self.node.remark, before)
        self.assertNotEqual(self.node.status, 'PAUSED')

        page = self.client.get(reverse('project_detail', args=[self.project.pk]))
        self.assertContains(page, '仅数据所有者可编辑此记录。')

    def test_member_failure_and_feedback_do_not_mutate(self):
        self.client.force_login(self.member)
        orders = set(self.project.nodes.values_list('order', flat=True))

        failed = self.client.post(
            reverse('node_failed', args=[self.node.pk]),
            {'remark': '不该写入'},
            HTTP_HX_REQUEST='true',
        )
        feedback = self.client.post(
            reverse('node_feedback', args=[self.node.pk]),
            {'feedback_type': 'CHANGE', 'remark': '不该插入'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(failed.status_code, 204)
        self.assertEqual(feedback.status_code, 204)
        self.node.refresh_from_db()
        self.assertNotEqual(self.node.status, 'FAILED')
        self.assertEqual(
            set(self.project.nodes.values_list('order', flat=True)),
            orders,
        )

    def test_manager_can_update_node(self):
        self.client.force_login(self.manager)
        resp = self.client.post(
            reverse('node_update', args=[self.node.pk]),
            {'status': 'PAUSED', 'remark': '负责人暂停'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 204)
        self.node.refresh_from_db()
        self.assertEqual(self.node.status, 'PAUSED')
        self.assertEqual(self.node.remark, '负责人暂停')

    def test_member_project_edit_stays_on_form_with_message(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse('project_edit', args=[self.project.pk]), {
            'code': self.project.code,
            'name': '被篡改的名称',
            'description': '',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '仅数据所有者可编辑此记录。')
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, '权限项目')

    def test_manager_can_edit_project_without_workflow(self):
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('project_edit', args=[self.project.pk]), {
            'code': self.project.code,
            'name': '负责人改名',
            'description': '说明',
        })
        self.assertEqual(resp.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, '负责人改名')

    def test_colleague_cannot_edit_repository(self):
        self.client.force_login(self.colleague)
        resp = self.client.post(reverse('repo_project_edit', args=[self.project.pk]), {
            'product_name': '同事改的',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '仅项目负责人或业务员可编辑此档案。')
        self.repo.refresh_from_db()
        self.assertEqual(self.repo.product_name, '原产品')

    def test_salesperson_and_manager_can_edit_repository(self):
        payload = {
            'salesperson': str(self.salesperson.pk),
            'submission_comment': '更名',
        }
        self.client.force_login(self.salesperson)
        resp = self.client.post(reverse('repo_project_edit', args=[self.project.pk]), {
            **payload, 'product_name': '业务员改的',
        })
        self.assertEqual(resp.status_code, 302, resp.content.decode()[:500] if resp.status_code != 302 else '')
        self.repo.refresh_from_db()
        self.assertEqual(self.repo.product_name, '业务员改的')

        self.client.force_login(self.manager)
        resp = self.client.post(reverse('repo_project_edit', args=[self.project.pk]), {
            **payload, 'product_name': '负责人改回',
        })
        self.assertEqual(resp.status_code, 302)
        self.repo.refresh_from_db()
        self.assertEqual(self.repo.product_name, '负责人改回')
