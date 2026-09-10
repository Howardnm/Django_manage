"""配方对比数据序列化层 — 把对比矩阵序列化为纯 JSON 数据契约。

数据来源：common_utils.comparison_matrix.build_compare_matrices(columns)
（columns 为 ORM 对象混 dict，需转纯 JSON）。

消费方：static/js/common/compare_table.js 通用表格组件（渲染两个对比入口 +
后续配色中心）。value 对象预留 meta 字段（feeding_port/is_pre_mix 等），
供配色中心扩展。

样式约定（与 common_utils/templatetags/project_extras.smart_decimal 一致）：
数值统一 _fmt() 格式化为字符串；空值 empty=True，由前端渲染淡色 '-'.
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList


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


def _fmt(value):
    """强制2位小数; 若第3位非0则显示3位（与 smart_decimal 一致）。"""
    if value is None:
        return '-'
    try:
        d = Decimal(str(value)).quantize(Decimal('0.001'))
    except Exception:
        return str(value)
    third = d.as_tuple().exponent
    if third == -3:
        if d.as_tuple().digits[-1] == 0:
            return '{:.2f}'.format(d)
        return '{:.3f}'.format(d)
    return '{:.2f}'.format(d)


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
# 批量价格计算（避免 N+1）
# ==========================================

def _compute_price_maps(raw_material_ids, months):
    """一次性批量计算原材料最新单价与近N月均价。

    语义与 RawMaterial.latest_price / avg_price 完全一致：
      latest_price = 最新日期的均价；无价格记录 → 缓存 _latest_price
      avg_price     = 近N月窗口内先按日均值、再对日均值求平均；窗口为空 → latest_price
    避免逐原材料触发属性聚合查询（原 N+1 热点）。

    Returns:
        (latest_map, avg_map) — {rm_id: Decimal|None}
    """
    from collections import defaultdict
    from datetime import date, timedelta

    from app_raw_material.models import RawMaterial, RawMaterialPriceRecord

    latest_map = {}
    avg_map = {}
    if not raw_material_ids:
        return latest_map, avg_map

    ids = list(raw_material_ids)

    # 缓存字段（无价格记录时回退用），一次性取回
    cached = {
        rm.pk: (rm._latest_price, rm._avg_price)
        for rm in RawMaterial.objects.filter(pk__in=ids).only('pk', '_latest_price', '_avg_price')
    }
    for rm_id in ids:
        _latest, _avg = cached.get(rm_id, (None, None))
        latest_map.setdefault(rm_id, _latest)
        avg_map.setdefault(rm_id, _avg)

    cutoff = date.today() - timedelta(days=months * 30)
    by_material = defaultdict(list)
    for r in RawMaterialPriceRecord.objects.filter(raw_material_id__in=ids).iterator():
        by_material[r.raw_material_id].append(r)

    for rm_id, rlist in by_material.items():
        _latest = cached.get(rm_id, (None, None))[0]

        # latest_price：最新日期均价
        max_date = max(r.date for r in rlist)
        day_prices = [r.price for r in rlist if r.date == max_date]
        latest = (sum(day_prices) / len(day_prices)).quantize(Decimal('0.01')) if day_prices else _latest
        latest_map[rm_id] = latest

        # avg_price：窗口内先按日均值，再对日均值求平均
        window = [r for r in rlist if r.date >= cutoff]
        if window:
            daily = defaultdict(list)
            for r in window:
                daily[r.date].append(r.price)
            daily_avg = [sum(v) / len(v) for v in daily.values()]
            overall = sum(daily_avg) / len(daily_avg)
            avg_map[rm_id] = overall.quantize(Decimal('0.01'))
        else:
            avg_map[rm_id] = latest

    return latest_map, avg_map


def _compute_unit_cost(f, avg_map, latest_map):
    """用批量价格 lookup 计算配方近N月均价成本（替代 LabFormula.unit_cost property）。

    逻辑与 LabFormula.unit_cost 一致：BOM 行 加权(avg_price or latest_price) 平均。
    """
    total_amount = Decimal('0.00')
    total_parts = Decimal('0.00')
    for line in f.bom_lines.all():
        total_parts += line.percentage
        price = avg_map.get(line.raw_material_id) or latest_map.get(line.raw_material_id)
        if price:
            total_amount += price * line.percentage
    if total_parts > 0:
        return (total_amount / total_parts).quantize(Decimal('0.01'))
    return getattr(f, '_unit_cost', None)


def _compute_cp_cost(cp, latest_map):
    """计算色粉预测成本（替代 ColorPowderBOM.cost property，避免 N+1）。

    逻辑一致：Σ(份数 × 最新单价) / 100；无有效条目 → None。
    """
    if cp is None:
        return None
    total = 0
    for e in cp.entries.all():
        if e.percentage:
            price = latest_map.get(e.raw_material_id) if latest_map else None
            if price:
                total += float(e.percentage) * float(price)
    return round(total / 100, 2) if total > 0 else None


# ==========================================
# 序列化入口
# ==========================================

def _serialize_column(c, project=None, latest_map=None, avg_map=None):
    """单列头 → dict。latest_map/avg_map 由 _compute_price_maps 批量算出，避免 N+1。"""
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
        latest = latest_map.get(obj.pk) if latest_map else getattr(obj, '_latest_price', None)
        return {
            'type': 'raw_material', 'id': obj.pk,
            'name': _get(obj, 'name'),
            'model_name': _get(obj, 'model_name'),
            'usage_method': _get(obj, 'usage_method'),
            'latest_price': _fmt(latest) if latest else '',
            'detail_url': reverse('raw_material_detail', args=[obj.pk]),
        }
    # formula
    name = _get(obj, 'name')
    stage_label = ''
    if obj.project_node:
        stage_label = f"{obj.project_node.get_stage_display()} 第{obj.project_node.round}轮"
    elif name.startswith('竞品-'):
        stage_label = '客户竞品'
    cp = getattr(obj, 'color_powder_bom', None)
    uc = _compute_unit_cost(obj, avg_map, latest_map) if (avg_map and latest_map) else getattr(obj, 'unit_cost', None)
    cp_cost = _compute_cp_cost(cp, latest_map) if cp else None
    return {
        'type': 'formula', 'id': obj.pk,
        'code': _get(obj, 'code'),
        'name': name,
        'stage_label': stage_label,
        'is_competitor': name.startswith('竞品-'),
        'is_mature': bool(getattr(obj, 'is_mature', False)),
        'is_foreign': bool(project and obj.project_id and obj.project_id != project.pk),
        'project_id': obj.project_id,
        'project_name': obj.project.name if getattr(obj, 'project', None) else '',
        'material_type_name': obj.material_type.name if getattr(obj, 'material_type', None) else '',
        'detail_url': reverse('formula_detail', args=[obj.pk]),
        'cost_predicted': _fmt(obj.cost_predicted) if getattr(obj, 'cost_predicted', None) else '',
        'unit_cost': _fmt(uc) if uc else '',
        'color_powder_cost': _fmt(cp_cost) if cp_cost else '',
        'process_id': obj.process_id,
        'process_name': obj.process.name if obj.process_id else '',
        'creator': obj.creator.username if obj.creator_id else '',
        'created_at': obj.created_at.strftime('%Y-%m-%d') if getattr(obj, 'created_at', None) else '',
        'description': _get(obj, 'description'),
    }


def _summary_section(key, label, icon, color, rows, band=False):
    return {'key': key, 'label': label, 'icon': icon, 'color': color, 'band': band, 'rows': rows}


def serialize_compare(columns, matrices, avg_months, project=None):
    """把 build_compare_matrices 的 ORM 混合结构 → 纯 JSON dict。

    Args:
        columns: [{'type': 'material'|'raw_material'|'formula', 'obj': <模型实例>}]
        matrices: (bom_matrix, cpbom_matrix, test_matrix) — build_compare_matrices 返回值
        avg_months: int
        project: Project | None（用于公式列的 史/本 徽章；None 时不区分来源）
    """
    bom_matrix, cpbom_matrix, test_matrix = matrices

    # 收集全部涉及原材料 → 批量算最新单价/近N月均价，避免逐属性聚合查询（N+1）
    raw_material_ids = set()
    for c in columns:
        if c['type'] == 'raw_material':
            raw_material_ids.add(c['obj'].pk)
        elif c['type'] == 'formula':
            for line in c['obj'].bom_lines.all():
                raw_material_ids.add(line.raw_material_id)
            cp = getattr(c['obj'], 'color_powder_bom', None)
            if cp:
                for e in cp.entries.all():
                    raw_material_ids.add(e.raw_material_id)
    for row in bom_matrix:
        raw_material_ids.add(row['item'].pk)
    for row in cpbom_matrix:
        raw_material_ids.add(row['item'].pk)
    latest_map, avg_map = _compute_price_maps(raw_material_ids, avg_months)

    serialized_columns = [_serialize_column(c, project, latest_map, avg_map) for c in columns]
    n = len(columns)

    def per_column(fn):
        return [fn(c) for c in columns]

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

    # ── 2. 预测成本 ──
    cost_values = []
    for c in columns:
        if c['type'] == 'material':
            cost_values.append(_val('-', empty=True))
        elif c['type'] == 'raw_material':
            latest = latest_map.get(c['obj'].pk)
            cost_values.append(_val(_fmt(latest) if latest else '-', empty=not latest))
        else:
            v = getattr(c['obj'], 'cost_predicted', None)
            cost_values.append(_val(_fmt(v) if v else '-', empty=not v))
    sections.append(_summary_section('cost', '预测成本', 'ti-currency-yen', 'green',
                                     [_row('预测成本', '-', '元/kg', cost_values)]))

    # ── 3. 近N月均价 ──
    avg_values = []
    for c in columns:
        v = _compute_unit_cost(c['obj'], avg_map, latest_map) if c['type'] == 'formula' else None
        avg_values.append(_val(_fmt(v) if v else '-', empty=not v))
    sections.append(_summary_section('avg_price', f'近{avg_months}月均价', 'ti-currency-yen', 'orange',
                                     [_row(f'近{avg_months}月均价', '-', '元/kg', avg_values)]))

    # ── 4. 色粉预测成本 ──
    cpcost_values = []
    for c in columns:
        cp = getattr(c['obj'], 'color_powder_bom', None) if c['type'] == 'formula' else None
        cost = _compute_cp_cost(cp, latest_map) if cp else None
        cpcost_values.append(_val(_fmt(cost) if cost else '-', empty=not cost))
    sections.append(_summary_section('cp_cost', '色粉预测成本', 'ti-palette', 'pink',
                                     [_row('色粉预测成本', '-', '元/kg', cpcost_values)]))

    # ── 5. BOM 结构对比 ──
    bom_rows = []
    for row in bom_matrix:
        rm = row['item']
        values = [_val(_fmt(cell['val']) if not cell['is_empty'] else '-',
                       empty=cell['is_empty']) for cell in row['values']]
        name2 = f"{rm.name} {rm.model_name}".strip() if getattr(rm, 'model_name', None) else rm.name
        bom_rows.append(_row(
            rm.category.name, name2, '%', values,
            label2_url=reverse('raw_material_detail', args=[rm.pk]),
            label2_sap=getattr(rm, 'warehouse_code', '') or '',
            label2_price=_fmt(latest_map.get(rm.pk)) if latest_map.get(rm.pk) else '',
        ))
    sections.append(_summary_section('bom', 'BOM 结构对比', 'ti-list', 'orange', bom_rows, band=True))

    # ── 6. 色粉BOM结构对比 ──
    cpbom_rows = []
    for row in cpbom_matrix:
        rm = row['item']
        values = [_val(_fmt(cell['val']) if not cell['is_empty'] else '-',
                       empty=cell['is_empty']) for cell in row['values']]
        name2 = f"{rm.name} {rm.model_name}".strip() if getattr(rm, 'model_name', None) else rm.name
        cpbom_rows.append(_row(
            rm.category.name, name2, '%', values,
            label2_url=reverse('raw_material_detail', args=[rm.pk]),
            label2_sap=getattr(rm, 'warehouse_code', '') or '',
            label2_price=_fmt(latest_map.get(rm.pk)) if latest_map.get(rm.pk) else '',
        ))
    sections.append(_summary_section('cpbom', '色粉BOM结构对比', 'ti-palette', 'pink', cpbom_rows, band=True))

    # ── 7. 性能指标对比 ──
    perf_rows = []
    for row in test_matrix:
        tc = row['item']
        values = [_val(_fmt(cell['val']), empty=(cell['val'] == '-'),
                       cls=cell.get('compare_class', ''), base=cell.get('is_base', False))
                  for cell in row['values']]
        label2 = tc.standard + (f" ({tc.condition})" if tc.condition else '')
        perf_rows.append(_row(tc.name, label2, tc.unit, values))
    sections.append(_summary_section('performance', '性能指标对比', 'ti-flask', 'purple', perf_rows, band=True))

    # ── 8. 工艺 & 基础信息 ──
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
