"""
app_process 伪数据生成器

业务逻辑：
  - MachineModel：挤出机型号库，关联 suitable_materials
  - ScrewCombination：螺杆组合，关联 machines + suitable_materials
  - ProcessProfile：工艺参数包，关联 machine + screw_combination + material_types
    遵循改性塑料挤出工艺的温区设定（喂料→熔融→排气→均化→机头）
"""

import random
from django.db import transaction
from ._base import (
    FakeContext, pick_one, pick, rand_decimal,
    COUNT_MACHINES, COUNT_SCREW_COMBINATIONS, COUNT_PROCESS_PROFILES,
)


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[5/13] Creating process data...")

    # --- MachineModel ---
    from app_process.models import MachineModel
    machine_brands = ["科倍隆", "莱斯特瑞兹", "JSW", "东芝", "南京科亚"]
    machines = []
    for i in range(COUNT_MACHINES):
        brand = machine_brands[i]
        model_name = f"{brand}-{random.randint(35, 95)}"
        obj, created = MachineModel.objects.get_or_create(
            model_name=model_name,
            defaults={
                'brand': brand,
                'machine_code': 100 + i,
                'screw_diameter': random.choice([35, 50, 65, 75, 95]),
                'ld_ratio': random.choice([32, 40, 44, 48, 52]),
                'motor_power': random.choice([55, 90, 160, 250, 400]),
                'max_speed': random.choice([600, 800, 1000, 1200]),
            },
        )
        if created:
            obj.suitable_materials.set(pick(ctx.material_types, random.randint(3, 8)))
        machines.append(obj)
    ctx.machines = machines

    # --- ScrewCombination ---
    from app_process.models import ScrewCombination
    screw_types = ['高剪切', '中剪切', '低剪切', '通用型', '阻燃专用', 'GF专用']
    screw_combinations = []
    for i in range(COUNT_SCREW_COMBINATIONS):
        obj, created = ScrewCombination.objects.get_or_create(
            name=f"螺杆组合-{screw_types[i % len(screw_types)]}{i + 1}",
            defaults={'combination_code': 200 + i},
        )
        if created:
            obj.machines.set(pick(machines, random.randint(1, 3)))
            obj.suitable_materials.set(pick(ctx.material_types, random.randint(3, 6)))
        screw_combinations.append(obj)
    ctx.screw_combinations = screw_combinations

    # --- ProcessProfile ---
    from app_process.models import ProcessProfile
    process_names = [
        'PP增强', 'PA6阻燃', 'PC/ABS', 'PA66-GF30',
        'PPS', '弹性体', '通用PP', 'PA6增韧',
    ]
    process_profiles = []
    for i in range(COUNT_PROCESS_PROFILES):
        machine = pick_one(machines)
        obj, created = ProcessProfile.objects.get_or_create(
            name=f"工艺-{machine.brand}-{process_names[i % len(process_names)]}",
            defaults={
                'machine': machine,
                'screw_combination': pick_one(screw_combinations),
                'screw_speed': random.randint(200, 800),
                'throughput': rand_decimal(100, 500, 1),
                'temp_zone_1': random.randint(180, 240),
                'temp_zone_2': random.randint(200, 260),
                'temp_zone_3': random.randint(210, 270),
                'temp_zone_4': random.randint(220, 280),
                'temp_zone_5': random.randint(220, 280),
                'temp_head': random.randint(230, 290),
                'melt_pressure': rand_decimal(20, 80, 1),
                'melt_temp': random.randint(230, 300),
                'vacuum': rand_decimal(-0.1, -0.06, 2),
                'main_feeder_speed': rand_decimal(20, 80, 1),
                'cooling_method': pick_one(['WATER_STRAND', 'WATER_RING', 'UNDERWATER']),
                'strand_count': random.randint(3, 12),
                'water_temp': random.randint(20, 35),
                'pelletizing_speed': rand_decimal(50, 200, 1),
                'creator': pick_one(ctx.rnd_users + ctx.proc_users),
            },
        )
        if created:
            obj.material_types.set(pick(ctx.material_types, random.randint(1, 4)))
        process_profiles.append(obj)
    ctx.process_profiles = process_profiles

    print(f"  machines={len(machines)}, screws={len(screw_combinations)}, "
          f"profiles={len(process_profiles)}")
