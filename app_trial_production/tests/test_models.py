"""ProductionOrder / ExtrusionTask / SampleInventory model tests."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from app_trial_production.models import (
    ProductionOrder, ExtrusionTask, SampleInventory, TrialProductionConfig,
)

User = get_user_model()


class ProductionOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='test')

    def test_code_auto_generation(self):
        """工单号自动生成格式 TP{YYYYMMDD}-{seq:02d}"""
        order = ProductionOrder.objects.create(creator=self.user)
        self.assertTrue(order.code.startswith('TP'))
        self.assertRegex(order.code, r'TP\d{8}-\d{2}')

    def test_code_sequence_increment(self):
        """同一日期的工单号序号递增"""
        order1 = ProductionOrder.objects.create(creator=self.user)
        order2 = ProductionOrder.objects.create(creator=self.user)
        seq1 = int(order1.code.split('-')[-1])
        seq2 = int(order2.code.split('-')[-1])
        self.assertEqual(seq2, seq1 + 1)

    def test_default_status_is_draft(self):
        """新工单默认状态为 DRAFT"""
        order = ProductionOrder.objects.create(creator=self.user)
        self.assertEqual(order.status, ProductionOrder.Status.DRAFT)

    def test_status_properties(self):
        """状态判断属性"""
        order = ProductionOrder.objects.create(creator=self.user)
        self.assertTrue(order.can_start_workflow)
        self.assertFalse(order.can_accept)
        self.assertFalse(order.can_start_extrusion)

    def test_status_css_class(self):
        """状态 CSS class 映射"""
        order = ProductionOrder.objects.create(creator=self.user)
        self.assertEqual(order.status_css_class, 'bg-secondary-lt')


class TrialProductionConfigTests(TestCase):
    def test_singleton_get(self):
        """全局配置单例 get_or_create"""
        config = TrialProductionConfig.get()
        self.assertEqual(config.pk, 1)
        config2 = TrialProductionConfig.get()
        self.assertEqual(config.pk, config2.pk)


class SampleInventoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='test')

    def test_can_sap_entry(self):
        """仅 FINISHED 颗粒 IN_LAB 状态可 SAP 入库"""
        order = ProductionOrder.objects.create(creator=self.user)
        sample = SampleInventory.objects.create(
            type='PELLET', sub_type='FINISHED', status='IN_LAB',
            production_order=order, quantity=10,
        )
        self.assertTrue(sample.can_sap_entry)

        sample.sub_type = 'FOR_INJECTION'
        self.assertFalse(sample.can_sap_entry)

    def test_is_reserved_for_injection(self):
        """FOR_INJECTION 颗粒关联注塑任务后标记为预留"""
        order = ProductionOrder.objects.create(creator=self.user)
        sample = SampleInventory.objects.create(
            type='PELLET', sub_type='FOR_INJECTION', status='IN_LAB',
            production_order=order, quantity=5,
        )
        self.assertFalse(sample.is_reserved_for_injection)
