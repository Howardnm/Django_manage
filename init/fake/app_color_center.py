"""
app_color_center 伪数据生成器

业务逻辑：
  - ColorMatchingTask：配色任务 — 读取 ctx.production_orders，为 ACCEPTED 之后的工单创建
  - 配色状态跟随工单状态推进：ACCEPTED→PENDING, EXTRUDING→IN_PROGRESS, INJECTION_MOLDING+→COMPLETED
  - 不需要配色的工单（needs_color_matching=False）状态为 NOT_REQUIRED
"""

import random
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from ._base import FakeContext, fake

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[12/16] Creating color center data...")

    if not ctx.production_orders:
        print("  No production orders — skipping ColorMatchingTask creation")
        return

    from app_color_center.models import ColorMatchingTask

    color_op = _get_or_create_operator("color_op", "COLOR_OPERATOR", ctx)

    AT_LEAST_ACCEPTED = ['ACCEPTED', 'EXTRUDING', 'INJECTION_MOLDING', 'TESTING', 'COMPLETED']
    AT_LEAST_EXTRUDING = ['EXTRUDING', 'INJECTION_MOLDING', 'TESTING', 'COMPLETED']
    AT_LEAST_INJECTION = ['INJECTION_MOLDING', 'TESTING', 'COMPLETED']

    color_task_count = 0
    for po in ctx.production_orders:
        if po.status not in AT_LEAST_ACCEPTED:
            continue

        # 从工单配方明细中判断是否需要配色
        needs_color = po.formula_details.filter(needs_color_matching=True).exists()

        color_status = 'NOT_REQUIRED' if not needs_color else 'PENDING'
        if needs_color:
            if po.status in AT_LEAST_EXTRUDING:
                color_status = 'IN_PROGRESS'
            if po.status in AT_LEAST_INJECTION:
                color_status = 'COMPLETED'

        ColorMatchingTask.objects.create(
            production_order=po,
            operator=color_op if needs_color and po.status in AT_LEAST_EXTRUDING else None,
            status=color_status,
            started_at=timezone.now() if needs_color and po.status in AT_LEAST_EXTRUDING else None,
            completed_at=timezone.now() if needs_color and po.status in AT_LEAST_INJECTION else None,
        )
        color_task_count += 1

    print(f"  color_tasks={color_task_count}")


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
