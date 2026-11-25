"""MoldType / InjectionTask model tests."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_mold_injection.models import MoldType, InjectionTask
from app_mold_injection.services import InjectionTaskService
from app_trial_production.models import ProductionOrder

User = get_user_model()


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
        """默认状态 PENDING"""
        task = InjectionTask()
        self.assertEqual(task.status, InjectionTask.Status.PENDING)

    def test_status_css_class(self):
        """各状态 CSS class 映射"""
        task = InjectionTask(status=InjectionTask.Status.PENDING)
        self.assertEqual(task.status_css_class, 'bg-secondary-lt')
        task.status = InjectionTask.Status.COMPLETED
        self.assertEqual(task.status_css_class, 'bg-green-lt')

    def test_complete_assigns_operator(self):
        user = User.objects.create_user(
            username='injector', email='injector@trial.dev', password='x')
        order = ProductionOrder.objects.create(creator=user, code='PO-INJ')
        task = InjectionTask.objects.create(production_order=order)

        InjectionTaskService.complete_task(task, user)

        task.refresh_from_db()
        self.assertEqual(task.operator_id, user.pk)
        self.assertEqual(task.status, InjectionTask.Status.COMPLETED)
