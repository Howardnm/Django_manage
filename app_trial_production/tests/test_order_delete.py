"""草稿工单删除的回归测试。

MoldRequirement.production_order 是不可空 CASCADE，与测试任务相同。
直接 order.delete() 应删掉模具需求及其配方明细，不能先把外键置空。
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_material.models import MaterialType, MetricCategory, TestConfig
from app_formula.models import FormulaTestResult, LabFormula
from app_mold_injection.models import (
    InjectionTask, MoldRequirement, MoldRequirementFormulaDetail, MoldType)
from app_trial_production.models import (
    ProductionOrder, ProductionOrderFormulaDetail)
from app_trial_production.services import ProductionOrderService

User = get_user_model()


class DraftOrderDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='order_owner', email='owner@trial.dev', password='x')
        self.mt = MaterialType.objects.create(name='PA66')
        self.formula = LabFormula.objects.create(
            code='T-5000', name='配方', material_type=self.mt,
            creator=self.user, version=1)
        self.order = ProductionOrder.objects.create(
            code='TP-5000', trial_code='T-5000',
            status=ProductionOrder.Status.DRAFT, creator=self.user)
        ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.formula, planned_quantity=10)
        self.mold = MoldType.objects.create(
            name='样条模具', mold_code='M-5000',
            mold_type=MoldType.MoldTypeChoices.TEST_SPECIMEN,
            standard=MoldType.Standard.ISO)
        requirement = MoldRequirement.objects.create(
            production_order=self.order, mold=self.mold, order=0)
        MoldRequirementFormulaDetail.objects.create(
            mold_requirement=requirement, formula=self.formula, specimen_quantity=2)
        self.client.force_login(self.user)

    def test_delete_draft_with_mold_requirements(self):
        """带模具矩阵的草稿工单必须能删掉（MySQL 上曾抛 CheckConstraint 违反）。"""
        ProductionOrderService.delete_draft(self.order)
        self.assertFalse(ProductionOrder.objects.filter(pk=self.order.pk).exists())
        self.assertFalse(MoldRequirement.objects.exists())
        self.assertFalse(MoldRequirementFormulaDetail.objects.exists())
        self.assertFalse(ProductionOrderFormulaDetail.objects.exists())
        self.assertTrue(MoldType.objects.filter(pk=self.mold.pk).exists())

    def test_order_delete_cascades_mold_requirements(self):
        """不可空 CASCADE：直接删工单，不先把模具需求的工单外键置空。"""
        injection = InjectionTask.objects.create(production_order=self.order)
        category = MetricCategory.objects.create(name='力学', order=1)
        config = TestConfig.objects.create(
            category=category, name='拉伸强度', standard='ISO 527', data_type='NUMBER')
        written = FormulaTestResult.objects.create(
            formula=self.formula, test_config=config, production_order=self.order,
            value='1.500')
        manual = FormulaTestResult.objects.create(
            formula=self.formula, test_config=config, value='2.000')

        self.order.delete()

        self.assertFalse(ProductionOrder.objects.filter(pk=self.order.pk).exists())
        self.assertFalse(MoldRequirement.objects.exists())
        self.assertFalse(MoldRequirementFormulaDetail.objects.exists())
        self.assertFalse(InjectionTask.objects.filter(pk=injection.pk).exists())
        self.assertFalse(FormulaTestResult.objects.filter(pk=written.pk).exists())
        self.assertTrue(FormulaTestResult.objects.filter(pk=manual.pk).exists())
        self.assertTrue(MoldType.objects.filter(pk=self.mold.pk).exists())

    def test_delete_draft_view(self):
        """「删除草稿」按钮走通同一路径。"""
        resp = self.client.post(
            reverse('trial_order_delete', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionOrder.objects.filter(pk=self.order.pk).exists())
