"""
app_trial_production 伪数据生成器【重构版】

业务逻辑（排产工单 + 挤出任务，下游模块独立）：
  TrialProductionConfig(单例)
    ↓
  ProductionOrder（工单号 TP{YYYYMMDD}-{NN}）
    ├── ProductionOrderFormulaDetail（配方明细）
    ├── ExtrusionTask（挤出任务，ACCEPTED 之后）
    └── SampleInventory(type=PELLET)（颗粒分拨，挤出完成后）

  ⚠ 下游模块由独立脚本生成：
    - app_color_center     → ColorMatchingTask（配色任务）
    - app_mold_injection   → MoldType + InjectionTask + MoldRequirement（注塑）
    - app_material_testing → TestingTask + TrialTestResult（测试）
"""

import random
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from ._base import (
    FakeContext, fake, pick_one, rand_decimal,
    COUNT_PRODUCTION_ORDERS,
)

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[10/16] Creating trial production data...")

    # =====================================================================
    # 1. TrialProductionConfig 单例
    # =====================================================================
    from app_trial_production.models.config import TrialProductionConfig

    config = TrialProductionConfig.get()
    if not config.workflow_definition:
        config.workflow_definition = pick_one(ctx.workflow_defs)
        config.save()

    # =====================================================================
    # 2. ProductionOrder + ExtrusionTask + SampleInventory(PELLET)
    # =====================================================================
    candidate_formulas = [
        f for f in ctx.formulas
        if f.project_node and f.project_node.stage in ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']
    ]
    if len(candidate_formulas) < COUNT_PRODUCTION_ORDERS:
        candidate_formulas = ctx.formulas

    from app_trial_production.models import (
        ProductionOrder, ProductionOrderFormulaDetail,
        ExtrusionTask, SampleInventory,
    )

    extruder_op = _get_or_create_operator("extruder_op", "EXTRUSION_OPERATOR", ctx)

    STATUS_CHOICES = [
        'DRAFT',
        'WORKFLOW_RUNNING',
        'ACCEPTED',
        'EXTRUDING',
        'INJECTION_MOLDING',
        'TESTING',
        'COMPLETED',
    ]

    AT_LEAST_ACCEPTED = STATUS_CHOICES[2:]
    AT_LEAST_EXTRUDING = STATUS_CHOICES[3:]

    production_orders = []
    for i in range(min(COUNT_PRODUCTION_ORDERS, len(candidate_formulas))):
        f = candidate_formulas[i]
        project = f.project
        p_node = f.project_node

        target_status = random.choice(STATUS_CHOICES)

        # --- 创建 ProductionOrder ---
        po = ProductionOrder.objects.create(
            trial_code=f.code,
            project=project,
            project_node=p_node,
            process_profile=f.process or pick_one(ctx.process_profiles),
            quantity_planned=rand_decimal(10, 50, 1),
            quantity_actual=(
                rand_decimal(8, 55, 1)
                if target_status in AT_LEAST_EXTRUDING
                else None
            ),
            creator=f.creator or pick_one(ctx.rnd_users),
            extruder_operator=(
                extruder_op if target_status in AT_LEAST_EXTRUDING else None
            ),
            status=target_status,
            remark=f"auto generated from {f.code}",
            completed_at=(
                timezone.now()
                if target_status == 'COMPLETED'
                else None
            ),
        )
        production_orders.append(po)

        # --- ProductionOrderFormulaDetail ---
        needs_color = random.random() < 0.4
        ProductionOrderFormulaDetail.objects.get_or_create(
            production_order=po,
            formula=f,
            defaults={
                'planned_quantity': po.quantity_planned,
                'needs_color_matching': needs_color,
            },
        )

        # --- ExtrusionTask（ACCEPTED 及之后） ---
        if target_status in AT_LEAST_ACCEPTED:
            ext_status = 'PENDING'
            if target_status in AT_LEAST_EXTRUDING:
                ext_status = 'IN_PROGRESS'
            if target_status in ['INJECTION_MOLDING', 'TESTING', 'COMPLETED']:
                ext_status = 'COMPLETED'

            extrusion_task = ExtrusionTask.objects.create(
                production_order=po,
                operator=extruder_op if target_status in AT_LEAST_EXTRUDING else None,
                status=ext_status,
                started_at=timezone.now() if target_status in AT_LEAST_EXTRUDING else None,
                completed_at=timezone.now() if target_status in ['INJECTION_MOLDING', 'TESTING', 'COMPLETED'] else None,
            )

            # 填充挤出参数
            if target_status in AT_LEAST_EXTRUDING:
                extrusion_task.temp_zone_1 = random.randint(180, 240)
                extrusion_task.temp_zone_2 = random.randint(200, 260)
                extrusion_task.temp_zone_3 = random.randint(210, 270)
                extrusion_task.temp_zone_4 = random.randint(220, 280)
                extrusion_task.temp_zone_5 = random.randint(220, 280)
                extrusion_task.temp_head = random.randint(230, 290)
                extrusion_task.screw_speed = random.randint(200, 800)
                extrusion_task.torque = round(random.uniform(40, 85), 1)
                extrusion_task.melt_pressure = round(random.uniform(20, 80), 1)
                extrusion_task.melt_temp = random.randint(230, 300)
                extrusion_task.vacuum = round(random.uniform(-0.1, -0.06), 2)
                extrusion_task.main_feeder_speed = round(random.uniform(20, 80), 1)
                extrusion_task.throughput = round(random.uniform(100, 500), 1)
                extrusion_task.cooling_method = pick_one([
                    'WATER_STRAND', 'WATER_RING', 'UNDERWATER',
                ])
                extrusion_task.strand_count = random.randint(3, 12)
                extrusion_task.water_temp = random.randint(20, 35)
                extrusion_task.pelletizing_speed = round(random.uniform(50, 200), 1)
                extrusion_task.recorded_by = extruder_op
                extrusion_task.save()

        # --- SampleInventory(PELLET) 颗粒分拨（EXTRUDING 及之后） ---
        if target_status in AT_LEAST_EXTRUDING:
            actual_qty = po.quantity_actual or Decimal('25')
            # 颗粒成品
            SampleInventory.objects.create(
                type='PELLET', sub_type='FINISHED',
                status=random.choice(['IN_LAB', 'IN_LAB', 'SAP_STORED']),
                production_order=po, formula=f,
                trial_code=po.trial_code,
                batch_number=f"{po.code}-V{f.version}",
                quantity=round(actual_qty * Decimal('0.6'), 1),
                packaging_desc=f"25kg/包 x {max(1, int(float(actual_qty * Decimal('0.6')) / 25) + 1)}包",
                storage_location=f"样品库-{random.choice(['A', 'B', 'C'])}区",
            )
            # 待打样颗粒
            SampleInventory.objects.create(
                type='PELLET', sub_type='FOR_INJECTION',
                status='IN_LAB',
                production_order=po, formula=f,
                trial_code=po.trial_code,
                batch_number=f"{po.code}-V{f.version}",
                quantity=round(actual_qty * Decimal('0.4'), 1),
                packaging_desc="待注塑打样",
                storage_location=f"样品库-{random.choice(['A', 'B', 'C'])}区",
            )

    ctx.production_orders = production_orders

    print(f"  production_orders={len(production_orders)}, "
          f"extrusion_tasks={ExtrusionTask.objects.count()}, "
          f"pellet_samples={SampleInventory.objects.filter(type='PELLET').count()}")


# ---------------------------------------------------------------------------
# 辅助：按需创建操作员用户
# ---------------------------------------------------------------------------
def _get_or_create_operator(username, role, ctx):
    """获取或创建指定角色的操作员用户"""
    user, created = User.objects.update_or_create(
        username=username,
        defaults={
            'user_type': role,
            'department': ctx.depts.get('PROCESS'),
            'user_level': random.randint(3, 10),
            'first_name': fake.name(),
            'email': f"{username}@sunwill.com.cn",
            'is_staff': False,
        },
    )
    if created:
        user.set_password('Sunwill@123')
    user.save()
    return user
