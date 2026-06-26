"""
app_user 伪数据生成器

业务逻辑：
  - 创建核心部门（研发/工艺/销售/供应链）
  - 按角色创建用户，密码统一为 Sunwill@123
  - 用户类型决定所属部门
"""

import random
from django.contrib.auth import get_user_model
from django.db import transaction
from ._base import FakeContext, fake, COUNT_RND, COUNT_PROCESS, COUNT_SALES, COUNT_PURCH

User = get_user_model()


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[1/16] Creating users & departments...")

    # --- 部门 ---
    from app_user.models import Department
    depts = {}
    for name, code in [
        ("研发中心", "RND"),
        ("工艺工程部", "PROCESS"),
        ("销售部", "SALES"),
        ("供应链中心", "PURCH"),
    ]:
        depts[code], _ = Department.objects.get_or_create(
            name=name, defaults={'code': code},
        )
    ctx.depts = depts

    # --- 用户创建辅助函数 ---
    def create_user(username, role, dept=None, level=1, customer=None, oem=None,
                    is_staff=False):
        user, created = User.objects.update_or_create(
            username=username,
            defaults={
                'user_type': role,
                'department': dept,
                'user_level': level,
                'associated_customer': customer,
                'associated_oem': oem,
                'first_name': fake.name(),
                'email': f"{username}@sunwill.com.cn",
                'phone': fake.phone_number(),
                'is_staff': is_staff,
            },
        )
        if created:
            user.set_password('Sunwill@123')
        user.save()
        return user

    # --- 管理员（仅此用户可登录后台） ---
    admin = create_user("admin", "ADMIN", depts['RND'], 15, is_staff=True)
    ctx.admin = admin

    # --- 研发工程师 ---
    ctx.rnd_users = [
        create_user(f"rnd_{i}", "ENGINEER", depts['RND'], random.randint(1, 15))
        for i in range(COUNT_RND)
    ]

    # --- 工艺工程师 ---
    ctx.proc_users = [
        create_user(f"proc_{i}", "PROCESS_ENGINEER", depts['PROCESS'], random.randint(3, 12))
        for i in range(COUNT_PROCESS)
    ]

    # --- 销售 ---
    ctx.sales_users = [
        create_user(f"sales_{i}", "SALES", depts['SALES'], random.randint(1, 10))
        for i in range(COUNT_SALES)
    ]

    # --- 采购 ---
    ctx.purch_users = [
        create_user(f"purch_{i}", "PURCHASING", depts['PURCH'], random.randint(1, 8))
        for i in range(COUNT_PURCH)
    ]

    ctx.all_internal = (
        ctx.rnd_users + ctx.proc_users + ctx.sales_users + ctx.purch_users + [admin]
    )

    print(f"  depts={len(depts)}, users={len(ctx.all_internal)} internal")
