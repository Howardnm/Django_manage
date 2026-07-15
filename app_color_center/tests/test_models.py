"""ColorMatchingTask model tests."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from app_color_center.models import ColorMatchingTask

User = get_user_model()


class ColorMatchingTaskTests(TestCase):
    def test_default_status_is_pending(self):
        """新建配色任务默认 PENDING"""
        task = ColorMatchingTask()
        self.assertEqual(task.status, ColorMatchingTask.Status.PENDING)

    def test_status_css_class(self):
        """各状态 CSS class 映射正确"""
        task = ColorMatchingTask(status=ColorMatchingTask.Status.PENDING)
        self.assertEqual(task.status_css_class, 'bg-orange-lt')
        task.status = ColorMatchingTask.Status.COMPLETED
        self.assertEqual(task.status_css_class, 'bg-green-lt')
        task.status = ColorMatchingTask.Status.NOT_REQUIRED
        self.assertEqual(task.status_css_class, 'bg-secondary-lt')

    def test_status_label(self):
        """状态中文显示"""
        task = ColorMatchingTask(status=ColorMatchingTask.Status.IN_PROGRESS)
        self.assertEqual(task.status_label, '配色中')
