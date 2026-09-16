"""草稿工单删除的回归测试。

针对 MySQL 上的一个隐蔽行为：MoldRequirement.production_order 是
null=True + CASCADE，Django 的 Collector 在无法延迟约束检查的后端上会先
`UPDATE ... SET production_order_id = NULL` 再删父行 —— 这一步会撞上
MoldRequirement 的 CheckConstraint(mold_req_has_production_order)。
直接把带模具矩阵的草稿工单 order.delete() 会抛 IntegrityError。
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_material.models import MaterialType
from app_formula.models import LabFormula
from app_mold_injection.models import MoldRequirement, MoldType
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
        mold = MoldType.objects.create(
            name='样条模具', mold_code='M-5000',
            mold_type=MoldType.MoldTypeChoices.TEST_SPECIMEN,
            standard=MoldType.Standard.ISO)
        MoldRequirement.objects.create(
            production_order=self.order, mold=mold, order=0)
        self.client.force_login(self.user)

    def test_delete_draft_with_mold_requirements(self):
        """带模具矩阵的草稿工单必须能删掉（MySQL 上曾抛 CheckConstraint 违反）。"""
        ProductionOrderService.delete_draft(self.order)
        self.assertFalse(ProductionOrder.objects.filter(pk=self.order.pk).exists())
        self.assertFalse(MoldRequirement.objects.exists())
        self.assertFalse(ProductionOrderFormulaDetail.objects.exists())

    def test_delete_draft_view(self):
        """「删除草稿」按钮走通同一路径。"""
        resp = self.client.post(
            reverse('trial_order_delete', kwargs={'pk': self.order.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ProductionOrder.objects.filter(pk=self.order.pk).exists())
