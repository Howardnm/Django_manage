"""
app_material 伪数据生成器

业务逻辑：
  - MaterialCharacteristic：材料特征属性主数据（高刚性、高韧性…）
  - MaterialLibrary：基于种子 MaterialType 创建材料牌号，关联特征和应用场景
  - MaterialDataPoint：每个材料的性能测试数据点，类型由 TestConfig 决定
"""

import random
from django.db import transaction
from ._base import FakeContext, pick_one, pick, rand_decimal, COUNT_MATERIALS


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[3/13] Creating material library...")

    # --- MaterialCharacteristic ---
    from app_material.models.material import MaterialCharacteristic
    characteristic_names = [
        "高刚性", "高韧性", "耐高温", "耐化学", "阻燃", "导电",
        "抗UV", "低翘曲", "高光泽", "免喷涂", "可降解", "轻量化",
    ]
    characteristics = []
    for name in characteristic_names:
        obj, _ = MaterialCharacteristic.objects.get_or_create(name=name)
        characteristics.append(obj)
    ctx.characteristics = characteristics

    # --- MaterialLibrary ---
    from app_material.models.material import MaterialLibrary, MaterialDataPoint

    manufacturer_names = ["金发", "普利特", "巴斯夫", "杜邦", "帝斯曼", "旭化成", "宝理"]
    flammability_choices = ["HB", "V-2", "V-0", "5VB"]
    prefix_list = ["G", "H", "K", "L", "M", "N", "P", "R", "S", "T", "X", "Z"]

    materials = []
    for i in range(COUNT_MATERIALS):
        prefix = prefix_list[i % len(prefix_list)]
        grade_name = (
            f"{prefix}{random.randint(100, 999)}"
            f"{random.choice(['A', 'B', 'C', ''])}"
            f"-{random.choice(['H', 'N', 'G', ''])}{random.randint(10, 99)}"
        )
        m, created = MaterialLibrary.objects.get_or_create(
            grade_name=grade_name,
            defaults={
                'manufacturer': pick_one(manufacturer_names),
                'category': pick_one(ctx.material_types),
                'is_published': random.random() < 0.7,
                'flammability': pick_one(flammability_choices),
            },
        )
        if created:
            m.characteristics.set(pick(characteristics, random.randint(2, 5)))
            m.scenarios.set(pick(ctx.scenarios, random.randint(1, 3)))
        materials.append(m)
    ctx.materials = materials

    # --- MaterialDataPoint ---
    dp_count = 0
    for m in materials:
        for tc in pick(ctx.test_configs, random.randint(8, 14)):
            value = None
            value_text = ""
            if tc.data_type == "NUMBER":
                value = rand_decimal(0.1, 500, 1)
            elif tc.data_type == "SELECT":
                value_text = pick_one(["V-0", "V-2", "HB", "Pass", "Fail", "合格"])
            _, created = MaterialDataPoint.objects.get_or_create(
                material=m, test_config=tc,
                defaults={'value': value, 'value_text': value_text},
            )
            if created:
                dp_count += 1

    print(f"  characteristics={len(characteristics)}, materials={len(materials)}, "
          f"data_points={dp_count}")
