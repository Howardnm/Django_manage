"""
app_repository 伪数据生成器

业务逻辑：
  - GradeFactor：等级因子影响项目评分权重（A级-1.50, B级-1.20, C级-1.00, D级-0.80）
  - Customer：直接客户公司（Tier 1/2），与 ProjectRepository 关联
"""

from django.db import transaction
from ._base import FakeContext, fake, COUNT_CUSTOMERS


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[2/13] Creating repository base data...")

    # --- GradeFactor ---
    from app_repository.models import GradeFactor
    grades = []
    for name, factor in [("A级", 1.50), ("B级", 1.20), ("C级", 1.00), ("D级", 0.80)]:
        obj, _ = GradeFactor.objects.get_or_create(
            name=name, defaults={'factor': factor},
        )
        grades.append(obj)
    ctx.grades = grades

    # --- Customer ---
    import random
    from app_repository.models import Customer

    customers = list(Customer.objects.all())
    if len(customers) < COUNT_CUSTOMERS:
        for i in range(COUNT_CUSTOMERS - len(customers)):
            name = f"{fake.company()}_{random.randint(100, 999)}"
            obj, _ = Customer.objects.get_or_create(
                company_name=name,
                defaults={
                    'short_name': name[:4],
                    'address': fake.address(),
                },
            )
            customers.append(obj)
    ctx.customers = customers

    print(f"  grades={len(grades)}, customers={len(customers)}")
