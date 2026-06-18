"""
app_trial_production 伪数据生成器【全新】

业务逻辑（遵循试生产完整工序流水线）：

  TrialProductionConfig(单例)  +  MoldType(模具台账)
    ↓
  ProductionOrder（工单号 TP{YYYYMMDD}-{NN}）
    ├── ProductionOrderFormulaDetail（配方明细）
    ├── ExtrusionRecord（挤出记录，EXTRUDING 之后）
    ├── ProductionOutput（产量记录）
    ├── SampleSplit → SampleInventory（样品分拨 → 样品库存）
    ├── InjectionMoldingOrder → MoldRequirement → SpecimenInventory（注塑 → 样条）
    └── TestingOrder → TrialTestResult（测试 → 回写中间结果）

状态推进：
  DRAFT → WORKFLOW_RUNNING → EXTRUDING → COLOR_POST →
  SAMPLE_SPLITTING → INJECTION_MOLDING → TESTING → COMPLETED
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
        ("ISO-178", "ISO", "TEST_SPECIMEN", "ISO 178 弯曲样条 80×10×4mm", 1),
        ("ISO-179", "ISO", "TEST_SPECIMEN", "ISO 179-1/1eA 缺口冲击样条", 1),
        ("ISO-75-HDT", "ISO", "TEST_SPECIMEN", "ISO 75 热变形温度样条 80×10×4mm", 2),
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
        'EXTRUDING',
        'COLOR_POST',
        'SAMPLE_SPLITTING',
        'INJECTION_MOLDING',
        'TESTING',
        'COMPLETED',
    ]

    # 每道工序前置状态集合
    AT_LEAST_EXTRUDING = STATUS_CHOICES[2:]   # EXTRUDING 及之后
    AT_LEAST_COLOR_POST = STATUS_CHOICES[3:]  # COLOR_POST 及之后
    AT_LEAST_SAMPLE_SPLIT = STATUS_CHOICES[4:] # SAMPLE_SPLITTING 及之后
    AT_LEAST_INJECTION = STATUS_CHOICES[5:]    # INJECTION_MOLDING 及之后
    AT_LEAST_TESTING = STATUS_CHOICES[6:]      # TESTING 及之后

    # =====================================================================
    # 4. ProductionOrder + 下游工序记录
    # =====================================================================
    # 选取公式中状态较前的（RND/PILOT/MID_TEST 阶段），模拟试产
    candidate_formulas = [
        f for f in ctx.formulas
        if f.project_node and f.project_node.stage in ['RND', 'PILOT', 'MID_TEST', 'MASS_PROD']
    ]
    if len(candidate_formulas) < COUNT_PRODUCTION_ORDERS:
        candidate_formulas = ctx.formulas

    from app_trial_production.models import (
        ProductionOrder, ProductionOrderFormulaDetail,
        ExtrusionRecord, ProductionOutput,
        SampleSplit, SampleInventory,
        InjectionMoldingOrder, MoldRequirement, SpecimenInventory,
        TestingOrder, TrialTestResult,
    )
    from app_material.models.material import TestConfig

    # 创建操作员用户（如果没有的话）
    extruder_op = _get_or_create_operator("extruder_op", "EXTRUSION_OPERATOR", ctx)
    color_op = _get_or_create_operator("color_op", "COLOR_OPERATOR", ctx)
    injection_op = _get_or_create_operator("injection_op", "INJECTION_OPERATOR", ctx)
    testing_op = _get_or_create_operator("testing_op", "TESTING_OPERATOR", ctx)

    production_orders = []
    injection_orders = []
    testing_orders = []

    for i in range(min(COUNT_PRODUCTION_ORDERS, len(candidate_formulas))):
        f = candidate_formulas[i]
        project = f.project
        p_node = f.project_node

        # 随机选择一个推进阶段
        target_status = random.choice(STATUS_CHOICES)

        # --- 创建 ProductionOrder ---
        po = ProductionOrder.objects.create(
            trial_code=f.code,  # 同批次配方共享实验单号
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
        # code 由 save() 自动生成
        production_orders.append(po)

        # --- ProductionOrderFormulaDetail ---
        ProductionOrderFormulaDetail.objects.get_or_create(
            production_order=po,
            formula=f,
            defaults={
                'planned_quantity': po.quantity_planned,
                'needs_color_matching': random.random() < 0.4,
            },
        )

        # --- ExtrusionRecord（EXTRUDING 及之后） ---
        if target_status in AT_LEAST_EXTRUDING:
            proc = po.process_profile
            ExtrusionRecord.objects.create(
                production_order=po,
                temp_zone_1=random.randint(180, 240),
                temp_zone_2=random.randint(200, 260),
                temp_zone_3=random.randint(210, 270),
                temp_zone_4=random.randint(220, 280),
                temp_zone_5=random.randint(220, 280),
                temp_head=random.randint(230, 290),
                screw_speed=random.randint(200, 800),
                torque=round(random.uniform(40, 85), 1),
                melt_pressure=round(random.uniform(20, 80), 1),
                melt_temp=random.randint(230, 300),
                vacuum=round(random.uniform(-0.1, -0.06), 2),
                main_feeder_speed=round(random.uniform(20, 80), 1),
                throughput=round(random.uniform(100, 500), 1),
                cooling_method=pick_one([
                    'WATER_STRAND', 'WATER_RING', 'UNDERWATER',
                ]),
                strand_count=random.randint(3, 12),
                water_temp=random.randint(20, 35),
                pelletizing_speed=round(random.uniform(50, 200), 1),
                recorded_by=extruder_op,
            )
            # ProductionOutput
            actual_qty = po.quantity_actual or rand_decimal(8, 50, 1)
            ProductionOutput.objects.create(
                production_order=po,
                total_output=actual_qty,
            )

        # --- SampleSplit + SampleInventory（COLOR_POST 及之后） ---
        if target_status in AT_LEAST_COLOR_POST:
            dest_choices = [
                ('SAMPLE_INVENTORY', 0.4),
                ('INJECTION_MOLDING', 0.4),
                ('RETAINED', 0.15),
                ('WASTE', 0.05),
            ]
            remaining = po.quantity_actual or Decimal('25')
            for dest, ratio in dest_choices:
                qty = round(remaining * Decimal(str(ratio)), 1)
                if qty <= 0:
                    continue
                split = SampleSplit.objects.create(
                    production_order=po,
                    formula=f,
                    destination=dest,
                    quantity=qty,
                    packaging_desc=f"25kg/包 × {max(1, int(qty / 25) + 1)}包",
                )
                if dest == 'SAMPLE_INVENTORY':
                    SampleInventory.objects.create(
                        sample_split=split,
                        production_order=po,
                        quantity=qty,
                        status=random.choice(['IN_STOCK', 'IN_STOCK', 'SHIPPED']),
                        storage_location=f"样品库-{random.choice(['A', 'B', 'C'])}区",
                        customer_name=(
                            fake.company()
                            if random.random() < 0.3
                            else ""
                        ),
                    )

        # --- InjectionMoldingOrder（INJECTION_MOLDING 及之后） ---
        if target_status in AT_LEAST_INJECTION:
            iom = InjectionMoldingOrder.objects.create(
                production_order=po,
                assigned_operator=injection_op,
                status=(
                    'COMPLETED'
                    if target_status in AT_LEAST_TESTING
                    else random.choice(['PENDING', 'IN_PROGRESS', 'COMPLETED'])
                ),
                injection_params_note=f"注塑参数-{po.code}" if random.random() < 0.5 else "",
            )
            injection_orders.append(iom)

            # MoldRequirement
            for mold in pick(mold_types, random.randint(1, min(3, len(mold_types)))):
                MoldRequirement.objects.create(
                    injection_order=iom,
                    mold=mold,
                    formula=f,
                    specimen_quantity=random.choice([5, 10, 20, 50]),
                    order=random.randint(0, 5),
                )

            # SpecimenInventory
            for mold in pick(mold_types, random.randint(1, 3)):
                qty_produced = random.randint(10, 100)
                SpecimenInventory.objects.create(
                    injection_order=iom,
                    mold=mold,
                    quantity_produced=qty_produced,
                    quantity_qualified=int(qty_produced * random.uniform(0.85, 1.0)),
                    storage_location=f"样条柜-{random.choice(['X', 'Y', 'Z'])}",
                    batch_label=f"BATCH-{po.code}-{mold.mold_code}",
                    status=(
                        'SENT_TO_TESTING'
                        if target_status in AT_LEAST_TESTING
                        else 'AVAILABLE'
                    ),
                )

        # --- TestingOrder + TrialTestResult（TESTING 及之后） ---
        if target_status in AT_LEAST_TESTING:
            test_items = pick(ctx.test_configs, random.randint(6, 12))
            specimens = list(SpecimenInventory.objects.filter(
                injection_order__production_order=po,
            ))
            to = TestingOrder.objects.create(
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
                to.test_items.set(test_items)
            if specimens:
                to.specimens.set(specimens)
            testing_orders.append(to)

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
                    testing_order=to,
                    test_config=tc,
                    formula=f,
                    value=value,
                    value_text=value_text,
                    test_date=rand_date(),
                    is_written_back=(target_status == 'COMPLETED'),
                )

    ctx.production_orders = production_orders
    ctx.injection_orders = injection_orders
    ctx.testing_orders = testing_orders

    print(f"  molds={len(mold_types)}, production_orders={len(production_orders)}, "
          f"extrusion={ExtrusionRecord.objects.count()}, "
          f"sample_splits={SampleSplit.objects.count()}, "
          f"injection_orders={InjectionMoldingOrder.objects.count()}, "
          f"specimens={SpecimenInventory.objects.count()}, "
          f"testing_orders={TestingOrder.objects.count()}, "
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
