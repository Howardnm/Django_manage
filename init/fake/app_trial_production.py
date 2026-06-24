"""
app_trial_production 伪数据生成器【重构版】

业务逻辑（遵循试生产完整工序流水线）：

  TrialProductionConfig(单例)  +  MoldType(模具台账)
    ↓
  ProductionOrder（工单号 TP{YYYYMMDD}-{NN}）
    ├── ProductionOrderFormulaDetail（配方明细）
    ├── ExtrusionTask（挤出任务，ACCEPTED 之后）
    ├── ColorMatchingTask（配色任务，ACCEPTED 之后，与挤出并行）
    ├── SampleInventory(type=PELLET)（颗粒分拨，挤出完成后）
    ├── InjectionTask → MoldRequirement → SampleInventory(type=SPECIMEN)（注塑 → 样条）
    └── TestingTask → TrialTestResult（测试 → 回写中间结果）

状态推进：
  DRAFT → WORKFLOW_RUNNING → ACCEPTED → EXTRUDING →
  INJECTION_MOLDING → TESTING → COMPLETED
"""

import random
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from ._base import (
    FakeContext, fake, pick_one, pick, rand_decimal, rand_date,
    COUNT_PRODUCTION_ORDERS, COUNT_MOLD_TYPES,
)

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[10/13] Creating trial production data...")

    # =====================================================================
    # 1. TrialProductionConfig 单例
    # =====================================================================
    from app_trial_production.models.config import TrialProductionConfig

    config = TrialProductionConfig.get()
    if not config.workflow_definition:
        config.workflow_definition = pick_one(ctx.workflow_defs)
        config.save()

    # =====================================================================
    # 2. MoldType 模具台账
    # =====================================================================
    from app_trial_production.models.mold import MoldType

    mold_defs = [
        ("ISO-527-1A", "ISO", "TEST_SPECIMEN", "ISO 527-2 1A 哑铃型拉伸样条", 1),
        ("ISO-178", "ISO", "TEST_SPECIMEN", "ISO 178 弯曲样条 80x10x4mm", 1),
        ("ISO-179", "ISO", "TEST_SPECIMEN", "ISO 179-1/1eA 缺口冲击样条", 1),
        ("ISO-75-HDT", "ISO", "TEST_SPECIMEN", "ISO 75 热变形温度样条 80x10x4mm", 2),
        ("ASTM-D638-TypeI", "ASTM", "TEST_SPECIMEN", "ASTM D638 Type I 拉伸样条", 1),
        ("GB-1040-1A", "GB", "TEST_SPECIMEN", "GB/T 1040.2-2006 1A型样条", 1),
    ]

    mold_types = []
    for i in range(COUNT_MOLD_TYPES):
        if i < len(mold_defs):
            desc, std, mtype, specimen, cavities = mold_defs[i]
            mold_code = f"MT-{std}-{i + 1:03d}"
            obj, created = MoldType.objects.get_or_create(
                mold_code=mold_code,
                defaults={
                    'name': f"{desc} 模具",
                    'mold_type': mtype,
                    'standard': std,
                    'specimen_description': specimen,
                    'cavity_count': cavities,
                    'status': 'AVAILABLE',
                },
            )
        else:
            obj = None
        if obj:
            mold_types.append(obj)
    ctx.mold_types = mold_types

    # =====================================================================
    # 3. 生产状态流水线定义
    # =====================================================================
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
    AT_LEAST_INJECTION = STATUS_CHOICES[4:]
    AT_LEAST_TESTING = STATUS_CHOICES[5:]

    # =====================================================================
    # 4. ProductionOrder + 下游工序记录
    # =====================================================================
    candidate_formulas = [
        f for f in ctx.formulas
        if f.project_node and f.project_node.stage in ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']
    ]
    if len(candidate_formulas) < COUNT_PRODUCTION_ORDERS:
        candidate_formulas = ctx.formulas

    from app_trial_production.models import (
        ProductionOrder, ProductionOrderFormulaDetail,
        ExtrusionTask, ColorMatchingTask,
        InjectionTask, MoldRequirement,
        TestingTask, TrialTestResult,
        SampleInventory,
    )
    from app_material.models.material import TestConfig

    extruder_op = _get_or_create_operator("extruder_op", "EXTRUSION_OPERATOR", ctx)
    color_op = _get_or_create_operator("color_op", "COLOR_OPERATOR", ctx)
    injection_op = _get_or_create_operator("injection_op", "INJECTION_OPERATOR", ctx)
    testing_op = _get_or_create_operator("testing_op", "TESTING_OPERATOR", ctx)

    production_orders = []
    injection_tasks = []
    testing_tasks = []

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

        # --- ExtrusionTask + ColorMatchingTask（ACCEPTED 及之后） ---
        if target_status in AT_LEAST_ACCEPTED:
            # 挤出任务
            ext_status = 'PENDING'
            if target_status in AT_LEAST_EXTRUDING:
                ext_status = 'IN_PROGRESS'
            if target_status in AT_LEAST_INJECTION:
                ext_status = 'COMPLETED'

            extrusion_task = ExtrusionTask.objects.create(
                production_order=po,
                operator=extruder_op if target_status in AT_LEAST_EXTRUDING else None,
                status=ext_status,
                started_at=timezone.now() if target_status in AT_LEAST_EXTRUDING else None,
                completed_at=timezone.now() if target_status in AT_LEAST_INJECTION else None,
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

            # 配色任务
            color_status = 'NOT_REQUIRED' if not needs_color else 'PENDING'
            if needs_color:
                if target_status in AT_LEAST_EXTRUDING:
                    color_status = 'IN_PROGRESS'
                if target_status in AT_LEAST_INJECTION:
                    color_status = 'COMPLETED'

            ColorMatchingTask.objects.create(
                production_order=po,
                operator=color_op if needs_color and target_status in AT_LEAST_EXTRUDING else None,
                status=color_status,
                started_at=timezone.now() if needs_color and target_status in AT_LEAST_EXTRUDING else None,
                completed_at=timezone.now() if needs_color and target_status in AT_LEAST_INJECTION else None,
            )

        # --- SampleInventory(PELLET) 颗粒分拨（EXTRUDING 及之后） ---
        if target_status in AT_LEAST_EXTRUDING:
            actual_qty = po.quantity_actual or Decimal('25')
            # 颗粒成品
            SampleInventory.objects.create(
                type='PELLET', sub_type='FINISHED',
                status=random.choice(['IN_LAB', 'IN_LAB', 'SAP_STORED']),
                production_order=po, formula=f,
                trial_code=po.trial_code,
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
                quantity=round(actual_qty * Decimal('0.4'), 1),
                packaging_desc="待注塑打样",
                storage_location=f"样品库-{random.choice(['A', 'B', 'C'])}区",
            )

        # --- InjectionTask（INJECTION_MOLDING 及之后） ---
        if target_status in AT_LEAST_INJECTION:
            it = InjectionTask.objects.create(
                production_order=po,
                source='ORDER',
                operator=injection_op,
                status=(
                    'COMPLETED'
                    if target_status in AT_LEAST_TESTING
                    else random.choice(['PENDING', 'IN_PROGRESS', 'COMPLETED'])
                ),
                injection_params_note=f"注塑参数-{po.code}" if random.random() < 0.5 else "",
                started_at=timezone.now(),
                completed_at=timezone.now() if target_status in AT_LEAST_TESTING else None,
            )
            injection_tasks.append(it)

            # MoldRequirement
            for mold in pick(mold_types, random.randint(1, min(3, len(mold_types)))):
                MoldRequirement.objects.create(
                    injection_task=it,
                    mold=mold,
                    formula=f,
                    specimen_quantity=random.choice([5, 10, 20, 50]),
                    order=random.randint(0, 5),
                )

            # SampleInventory(SPECIMEN) — 注塑产出的样条
            for mold in pick(mold_types, random.randint(1, 3)):
                qty_produced = random.randint(10, 100)
                SampleInventory.objects.create(
                    type='SPECIMEN',
                    sub_type='FOR_TESTING' if target_status not in AT_LEAST_TESTING else 'TESTED',
                    status='IN_LAB',
                    production_order=po, formula=f,
                    trial_code=po.trial_code,
                    specimen_count=qty_produced,
                    specimen_qualified=int(qty_produced * random.uniform(0.85, 1.0)),
                    storage_location=f"样条柜-{random.choice(['X', 'Y', 'Z'])}",
                    batch_label=f"BATCH-{po.code}-{mold.mold_code}",
                    injection_task=it,
                    mold=mold,
                )

        # --- TestingTask + TrialTestResult（TESTING 及之后） ---
        if target_status in AT_LEAST_TESTING:
            test_items = pick(ctx.test_configs, random.randint(6, 12))
            tt = TestingTask.objects.create(
                production_order=po,
                assigned_to=testing_op,
                status=(
                    'RESULTS_WRITTEN_BACK'
                    if target_status == 'COMPLETED'
                    else random.choice(['PENDING', 'IN_PROGRESS', 'COMPLETED'])
                ),
                completed_at=(
                    timezone.now()
                    if target_status == 'COMPLETED'
                    else None
                ),
            )
            if test_items:
                tt.test_items.set(test_items)
            testing_tasks.append(tt)

            # TrialTestResult
            for tc in test_items:
                value = None
                value_text = ""
                if tc.data_type == "NUMBER":
                    value = rand_decimal(0.05, 400, 1)
                elif tc.data_type == "SELECT":
                    value_text = pick_one(["V-0", "V-2", "HB", "Pass", "Fail", "合格"])
                else:
                    value_text = fake.text(10)
                TrialTestResult.objects.create(
                    testing_task=tt,
                    test_config=tc,
                    formula=f,
                    value=value,
                    value_text=value_text,
                    test_date=rand_date(),
                    is_written_back=(target_status == 'COMPLETED'),
                )

    ctx.production_orders = production_orders
    ctx.injection_orders = injection_tasks
    ctx.testing_orders = testing_tasks

    print(f"  molds={len(mold_types)}, production_orders={len(production_orders)}, "
          f"extrusion_tasks={ExtrusionTask.objects.count()}, "
          f"color_tasks={ColorMatchingTask.objects.count()}, "
          f"injection_tasks={InjectionTask.objects.count()}, "
          f"sample_inventory={SampleInventory.objects.count()}, "
          f"testing_tasks={TestingTask.objects.count()}, "
          f"trial_results={TrialTestResult.objects.count()}")


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
