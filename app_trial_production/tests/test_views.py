"""Basic view access tests."""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from app_user.models import UserRole

User = get_user_model()


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='engineer', email='engineer@trial.dev', password='test')
        # 设置为研发工程师身份以访问 dashboard
        self.user.user_type = UserRole.objects.create(code='R_ENGINEER', name='研发工程师')
        self.user.save()

    def test_dashboard_redirects_anonymous(self):
        """未登录用户重定向到登录页"""
        url = reverse('trial_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_dashboard_requires_auth(self):
        """dashboard 需要认证"""
        url = reverse('trial_dashboard')
        # 不登录直接访问
        response = self.client.get(url, follow=False)
        self.assertIn(response.status_code, [302, 403])


class ExtrusionBoardViewTests(TestCase):
    def test_board_redirects_anonymous(self):
        """排产工作台需要认证"""
        url = reverse('trial_extrusion_board')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
