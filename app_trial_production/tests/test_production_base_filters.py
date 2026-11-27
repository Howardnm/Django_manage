"""任务列表和待排产池按工单基地筛选。"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from app_color_center.filters import ColorTaskFilter
from app_material_testing.filters import TestingTaskFilter
from app_material_testing.models import TestingTask
from app_mold_injection.filters import InjectionTaskFilter
from app_mold_injection.models import InjectionTask
from app_trial_production.filters import ExtrusionTaskFilter, PendingOrderFilter
from app_trial_production.models import ExtrusionTask, ProductionOrder
from app_user.models import Subsidiary

User = get_user_model()


class ProductionBaseFilterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='base-filter', password='x')
        self.base_a = Subsidiary.objects.create(name='筛选基地A')
        self.base_b = Subsidiary.objects.create(name='筛选基地B')
        self.order_a = self._order(self.base_a)
        self.order_b = self._order(self.base_b)
        self.order_none = self._order(None)
        ExtrusionTask.objects.create(production_order=self.order_a)
        ExtrusionTask.objects.create(production_order=self.order_b)
        ExtrusionTask.objects.create(production_order=self.order_none)
        InjectionTask.objects.create(production_order=self.order_a)
        InjectionTask.objects.create(production_order=self.order_b)
        TestingTask.objects.create(production_order=self.order_a)
        TestingTask.objects.create(production_order=self.order_b)

    def _order(self, base):
        return ProductionOrder.objects.create(
            creator=self.user,
            production_base=base,
            status=ProductionOrder.Status.ACCEPTED,
        )

    def _pks(self, filterset):
        return set(filterset.qs.values_list('pk', flat=True))

    def test_unset_base_keeps_orders_without_base(self):
        found = self._pks(PendingOrderFilter({}, queryset=ProductionOrder.objects.all()))
        self.assertIn(self.order_none.pk, found)
        self.assertIn(self.order_a.pk, found)

    def test_pending_order_filter(self):
        found = self._pks(
            PendingOrderFilter({'production_base': self.base_a.pk}, queryset=ProductionOrder.objects.all()),
        )
        self.assertEqual(found, {self.order_a.pk})

    def test_color_task_filter(self):
        found = self._pks(
            ColorTaskFilter({'production_base': self.base_a.pk}, queryset=ProductionOrder.objects.all()),
        )
        self.assertEqual(found, {self.order_a.pk})

    def test_extrusion_task_filter(self):
        found = self._pks(
            ExtrusionTaskFilter({'production_base': self.base_b.pk}, queryset=ExtrusionTask.objects.all()),
        )
        self.assertEqual(found, {self.order_b.extrusion_task.pk})

    def test_injection_task_filter(self):
        found = self._pks(
            InjectionTaskFilter({'production_base': self.base_a.pk}, queryset=InjectionTask.objects.all()),
        )
        self.assertEqual(found, {self.order_a.injection_task.pk})

    def test_testing_task_filter(self):
        found = self._pks(
            TestingTaskFilter({'production_base': self.base_b.pk}, queryset=TestingTask.objects.all()),
        )
        self.assertEqual(
            found,
            set(self.order_b.testing_tasks.values_list('pk', flat=True)),
        )
