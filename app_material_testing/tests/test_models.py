"""TestingTask / TrialTestResult model tests."""
from django.test import TestCase
from app_material_testing.models import TestingTask, TrialTestResult


class TestingTaskTests(TestCase):
    def test_default_status_is_pending(self):
        """新建测试任务默认 PENDING"""
        task = TestingTask()
        self.assertEqual(task.status, TestingTask.Status.PENDING)

    def test_status_css_class(self):
        """各状态 CSS class 映射"""
        task = TestingTask(status=TestingTask.Status.PENDING)
        self.assertEqual(task.status_css_class, 'bg-secondary-lt')
        task.status = TestingTask.Status.IN_PROGRESS
        self.assertEqual(task.status_css_class, 'bg-yellow-lt')
        task.status = TestingTask.Status.COMPLETED
        self.assertEqual(task.status_css_class, 'bg-green-lt')
        task.status = TestingTask.Status.RESULTS_WRITTEN_BACK
        self.assertEqual(task.status_css_class, 'bg-info-lt')

    def test_status_label(self):
        """状态中文显示"""
        task = TestingTask(status=TestingTask.Status.RESULTS_WRITTEN_BACK)
        self.assertEqual(task.status_label, '已回写')
