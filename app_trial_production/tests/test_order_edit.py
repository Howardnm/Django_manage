"""排产工单的新建/编辑：计划产量校验。

工单的计划总产量不是表单字段，而是由各配方版本的 planned_qty_{pk} 汇总而来
（新建与编辑两个页面都是同一套规则，见 views/ProductionOrder.py 的
_resolve_planned_quantity）。全为 0、或全部留空的工单没有排产意义 ——
下游按 planned_quantity 摊投料量，全 0 会让 BOM 投料量整片变成 0。
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app_material.models import MaterialType
from app_formula.models import LabFormula
from app_project.models import Project
from app_trial_production.models import (
    ProductionOrder, ProductionOrderFormulaDetail)

User = get_user_model()


class OrderEditPlannedQuantityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username='order_editor', email='oe@trial.dev', password='x')
        self.mt = MaterialType.objects.create(name='PA66')
        self.v1 = LabFormula.objects.create(
            code='T-8000', name='配方v1', material_type=self.mt,
            creator=self.user, version=1)
        self.v2 = LabFormula.objects.create(
            code='T-8000', name='配方v2', material_type=self.mt,
            creator=self.user, version=2)

        self.order = ProductionOrder.objects.create(
            code='TP-8000', trial_code='T-8000',
            status=ProductionOrder.Status.DRAFT, creator=self.user)
        self.fd1 = ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.v1, planned_quantity=Decimal('25'))
        self.fd2 = ProductionOrderFormulaDetail.objects.create(
            production_order=self.order, formula=self.v2, planned_quantity=Decimal('15'))
        self.client.force_login(self.user)

    def _post(self, **quantities):
        """quantities 键为 "planned_qty_<fd.formula_id>"，缺省表示不提交该字段。"""
        data = {
            'mold-TOTAL_FORMS': '0',
            'mold-INITIAL_FORMS': '0',
            'mold-MIN_NUM_FORMS': '0',
            'mold-MAX_NUM_FORMS': '1000',
        }
        data.update(quantities)
        return self.client.post(
            reverse('trial_order_edit', kwargs={'pk': self.order.pk}), data)

    def _planned(self, detail):
        detail.refresh_from_db()
        return detail.planned_quantity

    def test_all_zero_is_rejected(self):
        resp = self._post(**{
            f'planned_qty_{self.fd1.formula_id}': '0',
            f'planned_qty_{self.fd2.formula_id}': '0',
        })
        self.assertEqual(resp.status_code, 200, '被拒后重渲染表单页')
        self.assertEqual(self._planned(self.fd1), Decimal('25'), '被拒时不得改动数据')
        self.assertEqual(self._planned(self.fd2), Decimal('15'))
        self.assertEqual(self.order.quantity_planned, Decimal('25.00'),
                         '被拒时不得重算计划总产量')

    def test_all_blank_is_rejected(self):
        """全部留空等价于全 0，同样必须拒绝。"""
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._planned(self.fd1), Decimal('25'))

    def test_single_positive_quantity_is_accepted(self):
        """只要有一个版本填了正数就放行。"""
        resp = self._post(**{
            f'planned_qty_{self.fd1.formula_id}': '30',
            f'planned_qty_{self.fd2.formula_id}': '0',
        })
        self.assertEqual(resp.status_code, 302, '应保存成功并重定向')
        self.assertEqual(self._planned(self.fd1), Decimal('30.000'))
        self.assertEqual(self._planned(self.fd2), Decimal('0.000'))

        self.order.refresh_from_db()
        self.assertEqual(self.order.quantity_planned, Decimal('30.00'),
                         '计划总产量应重算为各版本之和')

    def test_negative_total_is_rejected(self):
        """合计为负同样是无效排产（单列负数也不放行）。"""
        resp = self._post(**{
            f'planned_qty_{self.fd1.formula_id}': '-5',
            f'planned_qty_{self.fd2.formula_id}': '0',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._planned(self.fd1), Decimal('25'), '被拒时不得写入负数')

    def test_rejected_submit_keeps_typed_quantities(self):
        """被拦下来时要把用户刚填的值回显出来，而不是退回库里的旧值。

        用 -5 与 5（合计为 0）触发拒绝：两个值都与库里的 25/15 不同，
        所以只要能读到它们，就说明回显确实走了 POST。
        """
        resp = self._post(**{
            f'planned_qty_{self.fd1.formula_id}': '-5',
            f'planned_qty_{self.fd2.formula_id}': '5',
            f'needs_color_{self.fd1.formula_id}': 'on',
        })
        self.assertEqual(resp.status_code, 200, '合计为 0，应被拒')
        html = resp.content.decode('utf-8')
        self.assertIn('value="-5.0"', html, '应回显用户填的 -5')
        self.assertIn('value="5.0"', html, '应回显用户填的 5')
        self.assertIn('checked', html, '配色勾选也要回显')

class OrderCreatePlannedQuantityTests(TestCase):
    """创建页同样必须拒绝计划产量合计为 0 的工单。

    创建页原先没有这道关卡，而 ProductionOrderService.create_order() 在
    total_qty <= 0 时会跳过 order.save() —— 结果是工单已 INSERT、
    quantity_planned 停在模型默认值 25.0，各配方明细却全是 0，状态不自洽。
    """

    def setUp(self):
        self.user = User.objects.create_superuser(
            username='order_creator', email='oc@trial.dev', password='x')
        self.mt = MaterialType.objects.create(name='PA66')
        self.project = Project.objects.create(name='项目C', manager=self.user)
        self.trial_code = 'T-8100'
        self.v1 = LabFormula.objects.create(
            code=self.trial_code, name='配方v1', material_type=self.mt,
            project=self.project, creator=self.user, version=1)
        self.v2 = LabFormula.objects.create(
            code=self.trial_code, name='配方v2', material_type=self.mt,
            project=self.project, creator=self.user, version=2)
        self.client.force_login(self.user)

        # 创建页的 trial_formulas 取自 session（不是 POST），
        # 不设这一项的话重渲染时压根不会渲染出计划产量输入框
        session = self.client.session
        session['trial_initiate_data'] = {
            'trial_code': self.trial_code,
            'project_id': self.project.pk,
        }
        session.save()

    def _post(self, **quantities):
        data = {
            'quantity_planned': '25',
            'trial_code': self.trial_code,
            'project_id': self.project.pk,
            'mold-TOTAL_FORMS': '0',
            'mold-INITIAL_FORMS': '0',
            'mold-MIN_NUM_FORMS': '0',
            'mold-MAX_NUM_FORMS': '1000',
        }
        data.update(quantities)
        return self.client.post(reverse('trial_order_create'), data)

    def test_all_zero_is_rejected(self):
        resp = self._post(**{
            f'planned_qty_{self.v1.pk}': '0',
            f'planned_qty_{self.v2.pk}': '0',
        })
        self.assertEqual(resp.status_code, 200, '被拒后重渲染表单页')
        self.assertFalse(
            ProductionOrder.objects.filter(trial_code=self.trial_code).exists(),
            '被拒时不得留下工单（无论数量是否为默认值）')

    def test_all_blank_is_rejected(self):
        resp = self._post()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            ProductionOrder.objects.filter(trial_code=self.trial_code).exists())

    def test_positive_total_is_accepted(self):
        resp = self._post(**{
            f'planned_qty_{self.v1.pk}': '30',
            f'planned_qty_{self.v2.pk}': '5',
        })
        self.assertEqual(resp.status_code, 302, '应创建成功并重定向')

        order = ProductionOrder.objects.get(trial_code=self.trial_code)
        self.assertEqual(order.quantity_planned, Decimal('35.00'),
                         '计划总产量应为各版本之和')
        self.assertEqual(
            sorted(order.formula_details.values_list('planned_quantity', flat=True)),
            [Decimal('5.000'), Decimal('30.000')])

    def test_rejected_submit_keeps_typed_quantities(self):
        """创建页更依赖这个回显：没有工单时 map 恒为空，不回显就全部变回 0。"""
        resp = self._post(**{
            f'planned_qty_{self.v1.pk}': '-5',
            f'planned_qty_{self.v2.pk}': '5',
        })
        self.assertEqual(resp.status_code, 200, '合计为 0，应被拒')
        html = resp.content.decode('utf-8')
        self.assertIn('value="-5.0"', html, '应回显用户填的 -5，而不是重置为 0')
        self.assertIn('value="5.0"', html, '应回显用户填的 5')
