"""
配方对比矩阵构建 — 跨 app 复用的共享逻辑。

供 ProjectFormulaProcessView（配方过程页）与 FormulaCompareView（对比购物车页）复用，
避免两处各自实现一套 BOM / 色粉BOM / 性能对比矩阵。

约定：
    - columns 统一为 [{'type': 'material'|'raw_material'|'formula', 'obj': <模型实例>}, ...]
    - BOM / 色粉BOM 单元格统一 {'val': pct 或 '-', 'is_empty': bool}
    - 性能单元格统一 {'val', 'compare_class', 'is_base'}
    - 访问关联对象一律用 .all()，依赖调用方 prefetch，避免破坏 prefetch 缓存
"""


def build_compare_matrices(columns):
    """构建配方对比矩阵。

    Args:
        columns: list of {'type': 'material'|'raw_material'|'formula', 'obj': obj}
            - material.obj: MaterialLibrary（.properties 为物性值）
            - raw_material.obj: RawMaterial（.properties 为物性值）
            - formula.obj: LabFormula（.bom_lines / .test_results / .color_powder_bom）

    Returns:
        (bom_matrix, cpbom_matrix, test_matrix)
    """
    formula_columns = [c for c in columns if c['type'] == 'formula']

    # ---- BOM 对比矩阵（仅配方有 BOM） ----
    all_raw_materials = set()
    bom_map = {}  # {formula_id: {raw_material_id: percentage}}
    for c in formula_columns:
        f = c['obj']
        bom_map[f.id] = {}
        for line in f.bom_lines.all():
            all_raw_materials.add(line.raw_material)
            bom_map[f.id][line.raw_material_id] = line.percentage
    sorted_raw_materials = sorted(all_raw_materials, key=lambda x: (x.category.order, x.name))

    bom_matrix = []
    for rm in sorted_raw_materials:
        row = {'item': rm, 'values': []}
        for c in columns:
            if c['type'] == 'formula':
                pct = bom_map.get(c['obj'].id, {}).get(rm.id)
                row['values'].append({
                    'val': pct if pct is not None else '-',
                    'is_empty': pct is None,
                })
            else:
                # 材料/原材料没有 BOM
                row['values'].append({'val': '-', 'is_empty': True})
        bom_matrix.append(row)

    # ---- 色粉BOM 对比矩阵（仅配方有） ----
    all_cp_materials = set()
    cpbom_map = {}
    for c in formula_columns:
        f = c['obj']
        cpbom_map[f.id] = {}
        bom = getattr(f, 'color_powder_bom', None)
        if bom:
            for entry in bom.entries.all():
                all_cp_materials.add(entry.raw_material)
                cpbom_map[f.id][entry.raw_material_id] = entry.percentage
    sorted_cp_materials = sorted(all_cp_materials, key=lambda x: (x.category.order, x.name))

    cpbom_matrix = []
    for rm in sorted_cp_materials:
        row = {'item': rm, 'values': []}
        for c in columns:
            if c['type'] == 'formula':
                pct = cpbom_map.get(c['obj'].id, {}).get(rm.id)
                row['values'].append({
                    'val': pct if pct is not None else '-',
                    'is_empty': pct is None,
                })
            else:
                row['values'].append({'val': '-', 'is_empty': True})
        cpbom_matrix.append(row)

    # ---- 性能对比矩阵（基准 = 第一列） ----
    all_test_configs = set()
    col_props = {}  # {col_index: {test_config_id: value}}
    for i, c in enumerate(columns):
        props = {}
        obj = c['obj']
        if c['type'] == 'formula':
            for r in obj.test_results.all():
                if r.production_order_id is not None:
                    continue  # 跳过工单回写结果，仅对比手动录入
                all_test_configs.add(r.test_config)
                props[r.test_config_id] = (
                    r.value_text if r.test_config.data_type != 'NUMBER' else r.value
                )
        else:
            for p in obj.properties.all():
                all_test_configs.add(p.test_config)
                props[p.test_config_id] = (
                    p.value_text if p.test_config.data_type != 'NUMBER' else p.value
                )
        col_props[i] = props

    sorted_configs = sorted(all_test_configs, key=lambda x: (x.category.order, x.order))

    test_matrix = []
    for tc in sorted_configs:
        base_val = col_props.get(0, {}).get(tc.id)
        values = []
        for i, c in enumerate(columns):
            val = col_props.get(i, {}).get(tc.id)
            compare_class = ''
            # 仅数值类型与基准比较（从第二列开始）
            if i > 0 and val is not None and base_val is not None and tc.data_type == 'NUMBER':
                try:
                    if val > base_val:
                        compare_class = 'text-green'
                    elif val < base_val:
                        compare_class = 'text-red'
                except Exception:
                    pass
            values.append({
                'val': val if val is not None else '-',
                'compare_class': compare_class,
                'is_base': i == 0,
            })
        test_matrix.append({'item': tc, 'values': values})

    return bom_matrix, cpbom_matrix, test_matrix
