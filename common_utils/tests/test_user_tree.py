"""UserTreeAPIView：有部门但无工作组的用户应挂在部门节点下。"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_user.models import Department, ReviewGroup, WorkGroup
from common_utils.views import _user_tree_cache

User = get_user_model()


def _user_ids(nodes):
    found = []
    for node in nodes:
        if node['type'] == 'user':
            found.append(node['id'])
        found.extend(_user_ids(node.get('children') or []))
    return found


class UserTreePlacementTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(name='研发部')
        cls.dept_no_wg = Department.objects.create(name='市场部')
        cls.superuser = User.objects.create_superuser(
            username='tree_su', email='tree_su@x.com', password='x')

        cls.direct = User.objects.create_user(
            username='direct_user', email='direct@x.com', password='x',
            first_name='直属甲', department=cls.dept)
        cls.in_wg = User.objects.create_user(
            username='wg_user', email='wg@x.com', password='x',
            first_name='组员乙', department=cls.dept)
        cls.only_dept = User.objects.create_user(
            username='only_dept', email='only@x.com', password='x',
            first_name='市场丙', department=cls.dept_no_wg)
        cls.orphan = User.objects.create_user(
            username='orphan_user', email='orphan@x.com', password='x',
            first_name='无部门丁')
        cls.inactive = User.objects.create_user(
            username='inactive_user', email='inactive@x.com', password='x',
            first_name='停用戊', department=cls.dept, is_active=False)
        cls.review_only = User.objects.create_user(
            username='review_only', email='review@x.com', password='x',
            first_name='审核己', department=cls.dept)

        cls.wg = WorkGroup.objects.create(name='配方组', department=cls.dept, is_active=True)
        cls.wg.members.add(cls.in_wg)
        cls.rg = ReviewGroup.objects.create(name='评审组', is_active=True)
        cls.rg.members.add(cls.review_only)

    def setUp(self):
        _user_tree_cache['data'] = None
        _user_tree_cache['expires_at'] = 0
        self.client.force_login(self.superuser)

    def _nodes(self, query=''):
        url = reverse('user_tree_api')
        if query:
            url += f'?q={query}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return {node['id']: node for node in response.json()['nodes']}

    def test_department_user_without_workgroup_is_direct_child(self):
        nodes = self._nodes()
        dept = nodes[f'dept_{self.dept.pk}']
        direct_user_ids = [c['id'] for c in dept['children'] if c['type'] == 'user']
        self.assertIn(self.direct.pk, direct_user_ids)
        if 'other' in nodes:
            other_ids = [c['id'] for c in nodes['other']['children']]
            self.assertNotIn(self.direct.pk, other_ids)

    def test_department_without_workgroup_still_appears(self):
        nodes = self._nodes()
        dept = nodes[f'dept_{self.dept_no_wg.pk}']
        self.assertEqual(
            [c['id'] for c in dept['children'] if c['type'] == 'user'],
            [self.only_dept.pk],
        )

    def test_user_without_department_stays_in_other(self):
        nodes = self._nodes()
        other_ids = [c['id'] for c in nodes['other']['children']]
        self.assertIn(self.orphan.pk, other_ids)
        placed = []
        for node in nodes.values():
            if node['type'] == 'department':
                placed.extend(c['id'] for c in node['children'] if c['type'] == 'user')
        self.assertNotIn(self.orphan.pk, placed)

    def test_workgroup_member_is_not_duplicated_on_department(self):
        nodes = self._nodes()
        dept = nodes[f'dept_{self.dept.pk}']
        direct_user_ids = [c['id'] for c in dept['children'] if c['type'] == 'user']
        self.assertNotIn(self.in_wg.pk, direct_user_ids)
        wg = next(c for c in dept['children'] if c['id'] == f'wg_{self.wg.pk}')
        self.assertIn(self.in_wg.pk, [c['id'] for c in wg['children']])

    def test_review_group_only_user_stays_on_review_group(self):
        nodes = self._nodes()
        dept = nodes[f'dept_{self.dept.pk}']
        direct_user_ids = [c['id'] for c in dept['children'] if c['type'] == 'user']
        self.assertNotIn(self.review_only.pk, direct_user_ids)
        rg = nodes[f'rg_{self.rg.pk}']
        self.assertIn(self.review_only.pk, [c['id'] for c in rg['children']])

    def test_search_matches_direct_department_user(self):
        matched = self._nodes('直属甲')
        dept = matched[f'dept_{self.dept.pk}']
        self.assertIn(self.direct.pk, [c['id'] for c in dept['children'] if c['type'] == 'user'])
        self.assertNotIn(f'dept_{self.dept_no_wg.pk}', matched)

        missed = self._nodes('不存在的人')
        self.assertNotIn(self.direct.pk, _user_ids(missed.values()))

    def test_inactive_user_is_omitted(self):
        nodes = self._nodes()
        self.assertNotIn(self.inactive.pk, _user_ids(nodes.values()))
