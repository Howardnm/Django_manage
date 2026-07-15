"""MoldType / InjectionTask model tests."""
from django.test import TestCase
from app_mold_injection.models import MoldType, InjectionTask


class MoldTypeTests(TestCase):
    def test_status_css_class(self):
        """修复后的 status_css_class 属性"""
        mold = MoldType.objects.create(
            name='Test Mold', mold_code='TM-001',
            mold_type='TEST_SPECIMEN', standard='ISO',
        )
        self.assertEqual(mold.status_css_class, 'bg-green-lt')

        mold.status = MoldType.Status.MAINTENANCE
        self.assertEqual(mold.status_css_class, 'bg-yellow-lt')

        mold.status = MoldType.Status.RETIRED
        self.assertEqual(mold.status_css_class, 'bg-secondary-lt')

    def test_str_representation(self):
        """__str__ 格式：{mold_code} — {name}"""
        mold = MoldType.objects.create(
            name='ISO Tensile Bar Mold', mold_code='ISO-527-1A',
            mold_type='TEST_SPECIMEN', standard='ISO',
        )
        self.assertEqual(str(mold), 'ISO-527-1A — ISO Tensile Bar Mold')


class InjectionTaskTests(TestCase):
    def test_defaults(self):
        """默认状态 PENDING，默认来源 ORDER"""
        task = InjectionTask()
        self.assertEqual(task.status, InjectionTask.Status.PENDING)
        self.assertEqual(task.source, InjectionTask.Source.ORDER)

    def test_status_css_class(self):
        """各状态 CSS class 映射"""
        task = InjectionTask(status=InjectionTask.Status.PENDING)
        self.assertEqual(task.status_css_class, 'bg-secondary-lt')
        task.status = InjectionTask.Status.IN_PROGRESS
        self.assertEqual(task.status_css_class, 'bg-blue-lt')
        task.status = InjectionTask.Status.COMPLETED
        self.assertEqual(task.status_css_class, 'bg-green-lt')
