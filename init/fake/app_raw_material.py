"""
app_raw_material 伪数据生成器

业务逻辑：
  - 种子 RawMaterial 已由 import_raw_materials 命令导入
  - 在此基础上为原材料补充 RawMaterialProperty（物性指标）
  - 属性类型由 TestConfig.data_type 决定（数值/文本/选择）
"""

import random
from django.db import transaction
from ._base import FakeContext, pick_one, pick, rand_decimal


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[4/16] Creating raw material properties...")

    from app_raw_material.models import RawMaterialProperty

    rmp_count = 0
    sample_raw_materials = pick(ctx.raw_materials, min(15, len(ctx.raw_materials)))
    for rm in sample_raw_materials:
        for tc in pick(ctx.test_configs, random.randint(3, 8)):
            _, created = RawMaterialProperty.objects.get_or_create(
                raw_material=rm, test_config=tc,
                defaults={
                    'value': rand_decimal(0.1, 300, 1) if tc.data_type == "NUMBER" else None,
                    'value_text': pick_one(["合格", "优", "-"]) if tc.data_type != "NUMBER" else "",
                },
            )
            if created:
                rmp_count += 1

    print(f"  raw_material_properties={rmp_count} (from {len(sample_raw_materials)} raw materials)")
