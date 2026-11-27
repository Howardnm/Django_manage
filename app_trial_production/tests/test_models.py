"""ProductionOrder / ExtrusionTask model tests."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from app_trial_production.models import (
    ProductionOrder, ExtrusionTask, TrialProductionConfig,
)

User = get_user_model()


class ProductionOrderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='tp_models@trial.dev', password='test')

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

    def test_production_base_copied_from_creator(self):
        """创建时把创建人当前基地抄到工单上"""
        from app_user.models import Subsidiary
        base = Subsidiary.objects.create(name='上海基地', code='SH')
        self.user.subsidiary = base
        self.user.save(update_fields=['subsidiary'])
        order = ProductionOrder.objects.create(creator=self.user)
        self.assertEqual(order.production_base_id, base.pk)

    def test_production_base_null_when_creator_has_none(self):
        """创建人没填基地时工单基地留空，不拦截创建"""
        order = ProductionOrder.objects.create(creator=self.user)
        self.assertIsNone(order.production_base_id)

    def test_production_base_not_refreshed_after_creator_moves(self):
        """创建人以后调动，再保存工单不改已记录的基地"""
        from app_user.models import Subsidiary
        old = Subsidiary.objects.create(name='旧基地')
        new = Subsidiary.objects.create(name='新基地')
        self.user.subsidiary = old
        self.user.save(update_fields=['subsidiary'])
        order = ProductionOrder.objects.create(creator=self.user)
        self.user.subsidiary = new
        self.user.save(update_fields=['subsidiary'])
        order.remark = 'edited'
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.production_base_id, old.pk)


class TrialProductionConfigTests(TestCase):
    def test_singleton_get(self):
        """全局配置单例 get_or_create"""
        config = TrialProductionConfig.get()
        self.assertEqual(config.pk, 1)
        config2 = TrialProductionConfig.get()
        self.assertEqual(config.pk, config2.pk)
