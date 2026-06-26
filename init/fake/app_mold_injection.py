"""
app_mold_injection 伪数据生成器

业务逻辑：
  - MoldType：模具台账 — 不依赖其他模块，独立创建
  - InjectionTask：注塑任务 — 读取 ctx.production_orders，为 EXTRUDING 之后的工单创建
  - MoldRequirement + MoldRequirementFormulaDetail：模具需求矩阵 — 一个注塑任务下挂多个模具
  - SampleInventory(type=SPECIMEN)：注塑产出的样条样品
"""

import random
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from ._base import FakeContext, fake, pick_one, pick, COUNT_MOLD_TYPES

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[11/16] Creating mold injection data...")

    # =====================================================================
    # 1. MoldType 模具台账（独立创建，不依赖其他 fake 数据）
    # =====================================================================
    from app_mold_injection.models import (
        MoldType, InjectionTask, MoldRequirement, MoldRequirementFormulaDetail,
    )
    from app_trial_production.models import SampleInventory

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
    # 2. InjectionTask + MoldRequirement（依赖 ctx.production_orders）
    # =====================================================================
    if not ctx.production_orders:
        print("  No production orders — skipping InjectionTask creation")
        return

    injection_op = _get_or_create_operator("injection_op", "INJECTION_OPERATOR", ctx)

    # 只对 EXTRUDING 及之后状态的工单创建注塑任务
    AT_LEAST_INJECTION = ['INJECTION_MOLDING', 'TESTING', 'COMPLETED']

    injection_tasks = []
    for po in ctx.production_orders:
        if po.status not in AT_LEAST_INJECTION:
            continue

        f = po.formula_details.first()
        formula = f.formula if f else None

        it = InjectionTask.objects.create(
            production_order=po,
            source='ORDER',
            operator=injection_op,
            status=(
                'COMPLETED'
                if po.status in ['TESTING', 'COMPLETED']
                else random.choice(['PENDING', 'IN_PROGRESS', 'COMPLETED'])
            ),
            injection_params_note=f"注塑参数-{po.code}" if random.random() < 0.5 else "",
            started_at=timezone.now(),
            completed_at=timezone.now() if po.status in ['TESTING', 'COMPLETED'] else None,
        )
        injection_tasks.append(it)

        # MoldRequirement — 每个注塑任务随机选几个模具
        for mold in pick(mold_types, random.randint(1, min(3, len(mold_types)))):
            mr = MoldRequirement.objects.create(
                injection_task=it,
                production_order=po,
                mold=mold,
                order=random.randint(0, 5),
            )
            MoldRequirementFormulaDetail.objects.create(
                mold_requirement=mr,
                formula=formula,
                specimen_quantity=random.choice([5, 10, 20, 50]),
            )

        # SampleInventory(SPECIMEN) — 注塑产出的样条
        for mold in pick(mold_types, random.randint(1, 3)):
            qty_produced = random.randint(10, 100)
            sub_type = 'TESTED' if po.status in ['TESTING', 'COMPLETED'] else 'FOR_TESTING'
            SampleInventory.objects.create(
                type='SPECIMEN',
                sub_type=sub_type,
                status='IN_LAB',
                production_order=po,
                formula=formula,
                trial_code=po.trial_code,
                specimen_count=qty_produced,
                specimen_qualified=int(qty_produced * random.uniform(0.85, 1.0)),
                storage_location=f"样条柜-{random.choice(['X', 'Y', 'Z'])}",
                batch_label=f"BATCH-{po.code}-{mold.mold_code}",
                injection_task=it,
                mold=mold,
            )

    ctx.injection_orders = injection_tasks

    print(f"  molds={len(mold_types)}, injection_tasks={len(injection_tasks)}, "
          f"mold_requirements={MoldRequirement.objects.count()}")


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
