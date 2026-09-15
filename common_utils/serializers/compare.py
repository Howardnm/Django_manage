"""配方对比数据序列化层 — 把对比矩阵序列化为纯 JSON 数据契约。

数据来源：common_utils.comparison_matrix.build_compare_matrices(columns)
（columns 为 ORM 对象混 dict，需转纯 JSON）。

消费方：static/js/common/compare_table.js 通用表格组件（渲染两个对比入口 +
后续配色中心）。value 对象预留 meta 字段（feeding_port/is_pre_mix 等），
供配色中心扩展。

样式约定：数值统一 smart_decimal() 格式化为字符串（与模板 filter 同一实现）；
空值 empty=True，由前端渲染淡色 '-'.

本模块**不含任何价格/成本算术** —— 那些口径的唯一实现在
app_raw_material/services/price_service.py（价格聚合）与
app_formula/services/cost_service.py（Σ 加权成本）。
这里只负责把它们的结果序列化成前端契约。
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList

from common_utils.formatting import smart_decimal as _fmt


# ==========================================
# DRF 数据契约
# ==========================================

class CompareValueSerializer(serializers.Serializer):
    """单元格值。"""
    v = serializers.CharField(allow_null=True, allow_blank=True, required=False, default='')  # 展示字符串（已格式化）
    empty = serializers.BooleanField(default=True)                          # 空值 → 渲染淡色 '-'
    cls = serializers.CharField(allow_blank=True, default='', required=False)  # text-green / text-red
    base = serializers.BooleanField(default=False, required=False)          # 基准列高亮
    url = serializers.CharField(allow_blank=True, default='', required=False)  # 可选跳转链接


class CompareRowSerializer(serializers.Serializer):
    """一行 = 3 个固定列 + 每对比列一个值。"""
    label = serializers.CharField(allow_blank=True, default='-')      # 第一固定列（行名/原材料分类）
    label2 = serializers.CharField(allow_blank=True, default='-', required=False)  # 第二固定列（标准/原材料名）
    label2_url = serializers.CharField(allow_blank=True, default='', required=False)   # label2 可点击跳转链接（原材料详情）
    label2_sap = serializers.CharField(allow_blank=True, default='', required=False)   # 原材料 SAP/物料编码
    label2_price = serializers.CharField(allow_blank=True, default='', required=False) # 原材料最新单价
    unit = serializers.CharField(allow_blank=True, default='-', required=False)   # 第三固定列（单位）
    values = CompareValueSerializer(many=True)


class CompareSectionSerializer(serializers.Serializer):
    """一个分区 = 分区标题行 + 若干数据行。
    band=True: 渲染彩色分区条（BOM/性能/工艺）；band=False: 单行样式（描述/成本/均价/色粉成本）。
    """
    key = serializers.CharField(allow_blank=True)
    label = serializers.CharField(allow_blank=True)
    icon = serializers.CharField(allow_blank=True, default='', required=False)
    color = serializers.CharField(allow_blank=True, default='', required=False)  # blue/green/orange/pink/purple/cyan
    band = serializers.BooleanField(default=False, required=False)
    rows = CompareRowSerializer(many=True)


class CompareColumnSerializer(serializers.Serializer):
    """对比列头（type 判别，字段全可空，仅对应 type 使用）。"""
    type = serializers.CharField()
    id = serializers.IntegerField()
    # material / raw_material
    grade_name = serializers.CharField(allow_blank=True, default='', required=False)
    manufacturer = serializers.CharField(allow_blank=True, default='', required=False)
    name = serializers.CharField(allow_blank=True, default='', required=False)
    model_name = serializers.CharField(allow_blank=True, default='', required=False)
    usage_method = serializers.CharField(allow_blank=True, default='', required=False)
    latest_price = serializers.CharField(allow_blank=True, default='', required=False)
    # formula
    code = serializers.CharField(allow_blank=True, default='', required=False)
    stage_label = serializers.CharField(allow_blank=True, default='', required=False)
    is_competitor = serializers.BooleanField(default=False, required=False)
    is_mature = serializers.BooleanField(default=False, required=False)
    is_foreign = serializers.BooleanField(default=False, required=False)  # 跨项目来源 → 史 徽章
    project_id = serializers.IntegerField(allow_null=True, default=None, required=False)
    project_name = serializers.CharField(allow_blank=True, default='', required=False)
    material_type_name = serializers.CharField(allow_blank=True, default='', required=False)
    detail_url = serializers.CharField(allow_blank=True, default='', required=False)
    cost_predicted = serializers.CharField(allow_blank=True, default='', required=False)
    unit_cost = serializers.CharField(allow_blank=True, default='', required=False)
    color_powder_cost = serializers.CharField(allow_blank=True, default='', required=False)
    process_id = serializers.IntegerField(allow_null=True, default=None, required=False)
    process_name = serializers.CharField(allow_blank=True, default='', required=False)
    creator = serializers.CharField(allow_blank=True, default='', required=False)
    created_at = serializers.CharField(allow_blank=True, default='', required=False)
    description = serializers.CharField(allow_blank=True, default='', required=False)


class CompareDataSerializer(serializers.Serializer):
    avg_months = serializers.IntegerField()
    columns = CompareColumnSerializer(many=True)
    sections = CompareSectionSerializer(many=True)


# ==========================================
# 工具
# ==========================================

def as_plain(data):
    """DRF ReturnDict/ReturnList → 普通 dict/list。"""
    if isinstance(data, (ReturnDict, dict)):
        return {k: as_plain(v) for k, v in data.items()}
    if isinstance(data, (ReturnList, list, tuple)):
        return [as_plain(v) for v in data]
    if isinstance(data, Decimal):
        return float(data)
    return data


def _val(v='-', empty=True, cls='', base=False, url=''):
    return {'v': v, 'empty': empty, 'cls': cls, 'base': base, 'url': url}


def _row(label, label2, unit, values, label2_url='', label2_sap='', label2_price=''):
    return {
        'label': label, 'label2': label2, 'unit': unit, 'values': values,
        'label2_url': label2_url, 'label2_sap': label2_sap, 'label2_price': label2_price,
    }


def _get(obj, name):
    return getattr(obj, name, '') or ''


# ==========================================
# 序列化入口
# ==========================================

def _harvest_raw_material_ids(columns, bom_matrix, cpbom_matrix):
    """从本模块的输入结构里挑出「需要价格」的原材料 id。

    纯结构遍历，**不做任何算术** —— 本模块只认识 columns / matrices 的形状，
    价格与成本的实现分别在 app_raw_material / app_formula 的 service 层。

    除了配方自己 BOM 与色粉条目里的材料，还包括「作为对比列出现的原材料」：
    它们不属于任何配方，但列头要显示单价。
    """
    raw_material_ids = set()
    for c in columns:
        if c['type'] == 'raw_material':
            raw_material_ids.add(c['obj'].pk)
        elif c['type'] == 'formula':
            for line in c['obj'].bom_lines.all():
                raw_material_ids.add(line.raw_material_id)
            powder = getattr(c['obj'], 'color_powder_bom', None)
            if powder is not None:
                for entry in powder.entries.all():
                    raw_material_ids.add(entry.raw_material_id)
    for row in bom_matrix:
        raw_material_ids.add(row['item'].pk)
    for row in cpbom_matrix:
        raw_material_ids.add(row['item'].pk)
    return raw_material_ids


def _serialize_column(c, project, cost_calc):
    """单列头 → dict。cost_calc 由调用方建好，避免 N+1。"""
    prices = cost_calc.prices
    obj = c['obj']
    if c['type'] == 'material':
        return {
            'type': 'material', 'id': obj.pk,
            'grade_name': _get(obj, 'grade_name'),
            'manufacturer': _get(obj, 'manufacturer'),
            'description': _get(obj, 'description'),
            'detail_url': reverse('material_detail', args=[obj.pk]),
        }
    if c['type'] == 'raw_material':
        latest = prices.latest(obj.pk)
        return {
            'type': 'raw_material', 'id': obj.pk,
            'name': _get(obj, 'name'),
            'model_name': _get(obj, 'model_name'),
            'usage_method': _get(obj, 'usage_method'),
            'latest_price': _fmt(latest) if latest is not None else '',
            'detail_url': reverse('raw_material_detail', args=[obj.pk]),
        }
    # formula
    name = _get(obj, 'name')
    is_competitor = bool(getattr(obj, 'is_competitor', False))
    stage_label = ''
    if obj.project_node:
        stage_label = f"{obj.project_node.get_stage_display()} 第{obj.project_node.round}轮"
    elif is_competitor:
        stage_label = '客户竞品'
    cp = getattr(obj, 'color_powder_bom', None)
    uc = cost_calc.unit_cost(obj)
    predicted = cost_calc.predicted_cost(obj)
    cp_cost = cost_calc.powder_cost(cp) if cp is not None else None
    return {
        'type': 'formula', 'id': obj.pk,
        'code': _get(obj, 'code'),
        'name': name,
        'stage_label': stage_label,
        'is_competitor': is_competitor,
        'is_mature': bool(getattr(obj, 'is_mature', False)),
        'is_foreign': bool(project and obj.project_id and obj.project_id != project.pk),
        'project_id': obj.project_id,
        'project_name': obj.project.name if getattr(obj, 'project', None) else '',
        'material_type_name': obj.material_type.name if getattr(obj, 'material_type', None) else '',
        'detail_url': reverse('formula_detail', args=[obj.pk]),
        'cost_predicted': _fmt(predicted) if predicted is not None else '',
        'unit_cost': _fmt(uc) if uc is not None else '',
        'color_powder_cost': _fmt(cp_cost) if cp_cost is not None else '',
        'process_id': obj.process_id,
        'process_name': obj.process.name if obj.process_id else '',
        'creator': obj.creator.username if obj.creator_id else '',
        'created_at': obj.created_at.strftime('%Y-%m-%d') if getattr(obj, 'created_at', None) else '',
        'description': _get(obj, 'description'),
    }


def _summary_section(key, label, icon, color, rows, band=False):
    return {'key': key, 'label': label, 'icon': icon, 'color': color, 'band': band, 'rows': rows}


def serialize_compare(columns, matrices, avg_months, project=None, cost_calc=None):
    """把 build_compare_matrices 的 ORM 混合结构 → 纯 JSON dict。

    Args:
        columns: [{'type': 'material'|'raw_material'|'formula', 'obj': <模型实例>}]
        matrices: (bom_matrix, cpbom_matrix, test_matrix) — build_compare_matrices 返回值
        avg_months: int —— 「近N月均价」的 N，只用于分区标题。
            实际参与计算的是 cost_calc 装载时用的窗口，两者以下面这行取齐。
        project: Project | None（用于公式列的 史/本 徽章；None 时不区分来源）
        cost_calc: FormulaCostCalculator | None
            省略时按 columns 涉及的材料、以 avg_months 为窗口自建批量查表；
            传入则复用调用方已算好的结果（同一请求里还要导出 Excel，避免算两遍）。
    """
    bom_matrix, cpbom_matrix, test_matrix = matrices

    if cost_calc is None:
        # 成本的构造与计算都在 app_formula.services；这里只负责把
        # 「本模块输入结构里有哪些材料」告诉它
        from app_formula.services import FormulaCostCalculator
        cost_calc = FormulaCostCalculator.for_formulas(
            [c['obj'] for c in columns if c['type'] == 'formula'],
            months=avg_months,
            extra_raw_material_ids=_harvest_raw_material_ids(columns, bom_matrix, cpbom_matrix),
        )
    prices = cost_calc.prices
    # 标题里的 N 以实际窗口为准 —— 否则调用方传入的 avg_months 与
    # cost_calc 装载时用的 months 不一致时，标签会和数字对不上
    avg_months = prices.months

    serialized_columns = [_serialize_column(c, project, cost_calc) for c in columns]

    # ── 1. 描述/备注 ──
    desc_values = []
    for c in columns:
        if c['type'] == 'raw_material':
            txt = _get(c['obj'], 'usage_method')
        else:
            txt = _get(c['obj'], 'description')
        desc_values.append(_val(txt, empty=not txt))
    sections = [_summary_section('description', '描述/备注', 'ti-notes', 'blue',
                                 [_row('描述/备注', '-', '-', desc_values)])]

    # ── 2. 主BOM 预测成本 ──
    # 带「主BOM」前缀是为了和下面的「色粉预测成本」区分开 —— 两者都是成本，
    # 但一个按主配方 BOM 加权、一个按色粉配比折算。
    cost_label = '主BOM预测成本'
    cost_values = []
    for c in columns:
        if c['type'] == 'material':
            cost_values.append(_val('-', empty=True))
        elif c['type'] == 'raw_material':
            latest = prices.latest(c['obj'].pk)
            cost_values.append(_val(_fmt(latest) if latest is not None else '-',
                                    empty=latest is None))
        else:
            v = cost_calc.predicted_cost(c['obj'])
            cost_values.append(_val(_fmt(v) if v is not None else '-', empty=v is None))
    sections.append(_summary_section('cost', cost_label, 'ti-currency-yen', 'green',
                                     [_row(cost_label, '-', '元/kg', cost_values)]))

    # ── 3. 主BOM 近N月均价 ──
    avg_label = f'主BOM近{avg_months}月均价'
    avg_values = []
    for c in columns:
        v = cost_calc.unit_cost(c['obj']) if c['type'] == 'formula' else None
        avg_values.append(_val(_fmt(v) if v is not None else '-', empty=v is None))
    sections.append(_summary_section('avg_price', avg_label, 'ti-currency-yen', 'orange',
                                     [_row(avg_label, '-', '元/kg', avg_values)]))

    # ── 4. 色粉预测成本 ──
    cpcost_values = []
    for c in columns:
        cp = getattr(c['obj'], 'color_powder_bom', None) if c['type'] == 'formula' else None
        cost = cost_calc.powder_cost(cp) if cp is not None else None
        cpcost_values.append(_val(_fmt(cost) if cost is not None else '-', empty=cost is None))
    sections.append(_summary_section('cp_cost', '色粉预测成本', 'ti-palette', 'pink',
                                     [_row('色粉预测成本', '-', '元/kg', cpcost_values)]))

    # ── 5. 最新总成本（主BOM + 配色BOM）──
    # 「一公斤成品料的完整成本」= 上面两行最新口径成本之和；
    # 相加与缺价规则都在 FormulaCostCalculator.total_cost() 里
    total_label = '最新总成本'
    total_values = []
    for c in columns:
        v = cost_calc.total_cost(c['obj']) if c['type'] == 'formula' else None
        total_values.append(_val(_fmt(v) if v is not None else '-', empty=v is None))
    sections.append(_summary_section('total_cost', total_label, 'ti-calculator', 'cyan',
                                     [_row(total_label, '-', '元/kg', total_values)]))

    # ── 6. BOM 结构对比 ──
    bom_rows = []
    for row in bom_matrix:
        rm = row['item']
        values = [_val(_fmt(cell['val']) if not cell['is_empty'] else '-',
                       empty=cell['is_empty']) for cell in row['values']]
        name2 = f"{rm.name} {rm.model_name}".strip() if getattr(rm, 'model_name', None) else rm.name
        price = prices.latest(rm.pk)
        bom_rows.append(_row(
            rm.category.name, name2, '%', values,
            label2_url=reverse('raw_material_detail', args=[rm.pk]),
            label2_sap=getattr(rm, 'warehouse_code', '') or '',
            label2_price=_fmt(price) if price is not None else '',
        ))
    sections.append(_summary_section('bom', 'BOM 结构对比', 'ti-list', 'orange', bom_rows, band=True))

    # ── 7. 色粉BOM结构对比 ──
    cpbom_rows = []
    for row in cpbom_matrix:
        rm = row['item']
        values = [_val(_fmt(cell['val']) if not cell['is_empty'] else '-',
                       empty=cell['is_empty']) for cell in row['values']]
        name2 = f"{rm.name} {rm.model_name}".strip() if getattr(rm, 'model_name', None) else rm.name
        price = prices.latest(rm.pk)
        cpbom_rows.append(_row(
            rm.category.name, name2, '%', values,
            label2_url=reverse('raw_material_detail', args=[rm.pk]),
            label2_sap=getattr(rm, 'warehouse_code', '') or '',
            label2_price=_fmt(price) if price is not None else '',
        ))
    sections.append(_summary_section('cpbom', '色粉BOM结构对比', 'ti-palette', 'pink', cpbom_rows, band=True))

    # ── 8. 性能指标对比 ──
    perf_rows = []
    for row in test_matrix:
        tc = row['item']
        values = [_val(_fmt(cell['val']), empty=(cell['val'] == '-'),
                       cls=cell.get('compare_class', ''), base=cell.get('is_base', False))
                  for cell in row['values']]
        label2 = tc.standard + (f" ({tc.condition})" if tc.condition else '')
        perf_rows.append(_row(tc.name, label2, tc.unit, values))
    sections.append(_summary_section('performance', '性能指标对比', 'ti-flask', 'purple', perf_rows, band=True))

    # ── 9. 工艺 & 基础信息 ──
    proc_values, creator_values, date_values = [], [], []
    for c in columns:
        if c['type'] == 'formula':
            f = c['obj']
            if f.process_id:
                proc_values.append(_val(f.process.name, empty=False,
                                        url=reverse('process_profile_detail', args=[f.process.pk])))
            else:
                proc_values.append(_val('-', empty=True))
            creator_values.append(_val(f.creator.username if f.creator_id else '-',
                                       empty=not f.creator_id))
            created = f.created_at.strftime('%Y-%m-%d') if f.created_at else ''
            date_values.append(_val(created, empty=not created))
        else:
            proc_values.append(_val('-', empty=True))
            creator_values.append(_val('-', empty=True))
            date_values.append(_val('-', empty=True))
    sections.append(_summary_section(
        'process', '工艺 & 基础信息', 'ti-settings-cog', 'cyan',
        [_row('工艺方案', '-', '-', proc_values),
         _row('实验员', '-', '-', creator_values),
         _row('创建日期', '-', '-', date_values)],
        band=True))

    payload = {'avg_months': avg_months, 'columns': serialized_columns, 'sections': sections}
    ser = CompareDataSerializer(data=payload)
    ser.is_valid(raise_exception=True)
    return as_plain(ser.data)
