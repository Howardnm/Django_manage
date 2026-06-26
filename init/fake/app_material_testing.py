"""
app_material_testing 伪数据生成器

业务逻辑：
  - TestingTask：测试任务 — 读取 ctx.production_orders，为 TESTING 及之后的工单创建
  - TrialTestResult：测试中间结果 — 审批通过后回写到 FormulaTestResult
  - 测试结果按 TestConfig 编码，数值/文本/选择类型
"""

import random
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from ._base import FakeContext, fake, pick_one, pick, rand_decimal, rand_date

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[13/16] Creating material testing data...")

    if not ctx.production_orders:
        print("  No production orders — skipping TestingTask creation")
        return

    from app_material_testing.models import TestingTask, TrialTestResult

    testing_op = _get_or_create_operator("testing_op", "TESTING_OPERATOR", ctx)

    AT_LEAST_TESTING = ['TESTING', 'COMPLETED']

    testing_tasks = []
    for po in ctx.production_orders:
        if po.status not in AT_LEAST_TESTING:
            continue

        test_items = pick(ctx.test_configs, random.randint(6, 12))
        tt = TestingTask.objects.create(
            production_order=po,
            assigned_to=testing_op,
            status=(
                'RESULTS_WRITTEN_BACK'
                if po.status == 'COMPLETED'
                else random.choice(['PENDING', 'IN_PROGRESS', 'COMPLETED'])
            ),
            completed_at=(
                timezone.now()
                if po.status == 'COMPLETED'
                else None
            ),
        )
        if test_items:
            tt.test_items.set(test_items)
        testing_tasks.append(tt)

        # TrialTestResult — 为每个配方版本填写测试结果
        for fd in po.formula_details.all():
            formula = fd.formula
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
                    formula=formula,
                    value=value,
                    value_text=value_text,
                    test_date=rand_date(),
                    is_written_back=(po.status == 'COMPLETED'),
                )

    ctx.testing_orders = testing_tasks

    print(f"  testing_tasks={len(testing_tasks)}, "
          f"trial_results={TrialTestResult.objects.count()}")


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
