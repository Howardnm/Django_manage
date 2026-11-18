"""协同成员 / 销售成员工作量占比校验。"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from app_project.forms import ProjectMemberForm, ProjectSalesMemberForm
from app_project.models import Project

User = get_user_model()


class MemberWorkloadFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(
            username='form_mgr', email='form_mgr@test.local', password='x',
        )
        cls.user_a = User.objects.create_user(
            username='form_a', email='form_a@test.local', password='x',
        )
        cls.user_b = User.objects.create_user(
            username='form_b', email='form_b@test.local', password='x',
        )
        cls.inactive = User.objects.create_user(
            username='form_off', email='form_off@test.local', password='x', is_active=False,
        )
        cls.project = Project.objects.create(code='FORM-1', name='表单项目', manager=cls.manager)
        cls.project.members.create(user=cls.user_a, role='RND', workload_share=Decimal('60'))
        cls.project.sales_members.create(user=cls.user_a, workload_share=Decimal('80'))

    def test_member_share_cannot_exceed_remaining_quota(self):
        form = ProjectMemberForm(
            {'user': str(self.user_b.pk), 'role': 'RND', 'workload_share': '50'},
            project=self.project,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('workload_share', form.errors)
        self.assertIn('40%', form.errors['workload_share'][0])

    def test_member_share_rejects_fraction_and_inactive_user(self):
        fraction = ProjectMemberForm(
            {'user': str(self.user_b.pk), 'role': 'RND', 'workload_share': '10.5'},
            project=self.project,
        )
        self.assertFalse(fraction.is_valid())
        self.assertIn('整数', fraction.errors['workload_share'][0])

        inactive = ProjectMemberForm(
            {'user': str(self.inactive.pk), 'role': 'RND', 'workload_share': '10'},
            project=self.project,
        )
        self.assertFalse(inactive.is_valid())
        self.assertIn('user', inactive.errors)

    def test_editing_member_excludes_own_share_from_quota(self):
        member = self.project.members.get(user=self.user_a)
        form = ProjectMemberForm(
            {'user': str(self.user_a.pk), 'role': 'RND', 'workload_share': '100'},
            instance=member,
            project=self.project,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_sales_share_uses_its_own_pool(self):
        over = ProjectSalesMemberForm(
            {'user': str(self.user_b.pk), 'workload_share': '30'},
            project=self.project,
        )
        self.assertFalse(over.is_valid())
        self.assertIn('销售总工作量', over.errors['workload_share'][0])

        ok = ProjectSalesMemberForm(
            {'user': str(self.user_b.pk), 'workload_share': '20'},
            project=self.project,
        )
        self.assertTrue(ok.is_valid(), ok.errors)
