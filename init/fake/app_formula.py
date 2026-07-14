"""
app_formula 伪数据生成器

业务逻辑：
  - LabFormula：实验配方的 code 自动生成（L{YYYYMMDD}-{NN}），(code, version) 联合唯一
  - FormulaBOM：BOM 明细行，百分比之和趋近 100%，含尾料/预混标记
  - FormulaTestResult：测试结果按 TestConfig 编码，数值/文本/选择类型
  - ColorPowderBOM + ColorPowderBOMEntry：色粉配比表（配色部门在试产后填写）
  - 多版本配方：v2~v4，BOM 和测试结果基于上一版本微调
"""

import re
import random
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from ._base import FakeContext, fake, pick_one, pick, rand_decimal, rand_date, COUNT_FORMULAS


@transaction.atomic
def run(ctx: FakeContext) -> None:
    print("\n[9/16] Creating formulas...")

    from app_formula.models import (
        LabFormula, FormulaBOM, FormulaTestResult,
        ColorPowderBOM, ColorPowderBOMEntry,
    )

    feeding_ports = ['1_MAIN', '2_SIDE_1', '3_SIDE_2', '4_LIQUID']
    weighing_scales = ['A', 'B', 'C', 'D', 'E']

    formulas = []
    for i in range(COUNT_FORMULAS):
        project = pick_one(ctx.projects)
        p_nodes = list(project.nodes.filter(
            stage__in=['RND', 'PILOT', 'MID_TEST', 'MASS_PROD'],
        ))
        p_node = pick_one(p_nodes) if p_nodes else None

        # 生成唯一 code：Python 端取最大数字后缀，规避字符串排序 bug
        code_prefix = f"L{timezone.now().strftime('%Y%m%d')}"
        existing_codes = LabFormula.objects.filter(
            code__startswith=code_prefix,
        ).values_list('code', flat=True)
        max_seq = 0
        for c in existing_codes:
            m = re.search(r'-(\d+)$', c)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
        seq = max_seq + 1
        code = f"{code_prefix}-{seq:02d}"

        # 随机颜色信息
        color_names = ["哑光黑", "亮白", "透明蓝", "碳灰", "象牙白", "钢琴黑", "", ""]
        pantone_codes = [
            "PANTONE 19-4052 Classic Blue",
            "PANTONE 18-1664 Fiery Red",
            "PANTONE 14-4103 Gray Violet",
            "PANTONE 11-0601 Bright White",
            "", "", "", "",
        ]
        rgb_values = ["#2C3E50", "#E74C3C", "#8E44AD", "#F1F1F1", "#1A1A1A", "", "", ""]

        f = LabFormula.objects.create(
            code=code,
            name=f"{project.name} - {p_node.get_stage_display() if p_node else 'RND'} formula",
            material_type=pick_one(ctx.material_types),
            process=pick_one(ctx.process_profiles) if random.random() < 0.3 else None,
            project=project,
            project_node=p_node,
            version=1,
            creator=pick_one(ctx.rnd_users),
            cost_predicted=rand_decimal(10, 50, 2),
            unit_cost=rand_decimal(12, 55, 2) if random.random() < 0.4 else None,
            material_color_name=random.choice(color_names),
            pantone_code=random.choice(pantone_codes),
            rgb_value=random.choice(rgb_values),
            description=fake.text(60) if random.random() < 0.5 else "",
        )

        # --- BOM ---
        bom_mats = pick(ctx.raw_materials, random.randint(5, 10))
        total = Decimal('0')
        for j, rm in enumerate(bom_mats):
            rem = len(bom_mats) - j - 1
            pct = (
                Decimal('100') - total
                if rem == 0
                else rand_decimal(1, max(1, float(100 - total) - rem), 2)
            )
            total += pct
            FormulaBOM.objects.create(
                formula=f,
                feeding_port=pick_one(feeding_ports),
                weighing_scale=pick_one(weighing_scales),
                raw_material=rm,
                percentage=pct,
                is_tail=random.random() < 0.15,
                is_pre_mix=random.random() < 0.2,
                pre_mix_order=random.randint(0, 3) if random.random() < 0.2 else 0,
            )

        # --- Test Results ---
        for tc in pick(ctx.test_configs, random.randint(8, 16)):
            value = None
            value_text = ""
            if random.random() < 0.6:
                if tc.data_type == "NUMBER":
                    value = rand_decimal(0.05, 400, 1)
                elif tc.data_type == "SELECT":
                    value_text = pick_one(["V-0", "V-2", "HB", "Pass", "Fail"])
                else:
                    value_text = fake.text(10)
            if value is not None or value_text:
                FormulaTestResult.objects.create(
                    formula=f, test_config=tc,
                    value=value, value_text=value_text,
                    test_date=rand_date() if random.random() < 0.7 else None,
                )
        formulas.append(f)

    # --- 多版本配方 ---
    for f in pick(formulas, 5):
        for v in range(2, random.randint(2, 4)):
            f2, created = LabFormula.objects.get_or_create(
                code=f.code, version=v,
                defaults={
                    'name': f"{f.name} v{v}",
                    'material_type': f.material_type,
                    'process': f.process,
                    'project': f.project,
                    'project_node': f.project_node,
                    'creator': f.creator,
                    'cost_predicted': f.cost_predicted,
                    'description': f.description,
                },
            )
            if not created:
                continue
            for b in f.bom_lines.all():
                FormulaBOM.objects.create(
                    formula=f2, feeding_port=b.feeding_port,
                    weighing_scale=b.weighing_scale, raw_material=b.raw_material,
                    percentage=(
                        b.percentage + rand_decimal(-5, 5, 2)
                        if random.random() < 0.3
                        else b.percentage
                    ),
                    is_tail=b.is_tail, is_pre_mix=b.is_pre_mix,
                    pre_mix_order=b.pre_mix_order,
                )
            for t in f.test_results.all()[:5]:
                FormulaTestResult.objects.create(
                    formula=f2, test_config=t.test_config,
                    value=(
                        t.value + rand_decimal(-5, 5, 1)
                        if t.value and random.random() < 0.4
                        else t.value
                    ),
                    value_text=t.value_text,
                    test_date=rand_date(),
                )

    # --- ColorPowderBOM（新增：色粉配比） ---
    # 为部分成熟配方创建色粉配比表
    color_powder_count = 0
    for f in pick(formulas, 6):
        if f.bom_lines.count() == 0:
            continue
        bom, _ = ColorPowderBOM.objects.get_or_create(
            formula=f,
            defaults={
                'filled_by': pick_one(ctx.proc_users),
                'remark': 'auto generated color powder BOM',
            },
        )
        # 创建色粉明细（从原材料中选取色粉/助剂类材料）
        color_mats = pick(ctx.raw_materials, random.randint(1, 4))
        for rm in color_mats:
            ColorPowderBOMEntry.objects.create(
                color_powder_bom=bom,
                feeding_port='4_LIQUID',
                weighing_scale='D',  # 色粉/微量秤
                raw_material=rm,
                percentage=rand_decimal(0.1, 3, 2),
                is_pre_mix=True,
                pre_mix_order=random.randint(1, 3),
            )
        color_powder_count += 1

    ctx.formulas = list(LabFormula.objects.all())

    print(f"  formulas={LabFormula.objects.count()}, "
          f"BOM={FormulaBOM.objects.count()}, "
          f"tests={FormulaTestResult.objects.count()}, "
          f"color_powder_boms={color_powder_count}")
