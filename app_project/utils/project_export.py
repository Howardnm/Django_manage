"""把全部项目导出为 xlsx 字节。只查当前数据库，只在内存里组表，不写盘。"""
from io import BytesIO

from django.utils import timezone

from app_project.models import Project, ProjectStage

BASE_HEADERS = (
    '项目编号', '项目名称', '项目等级', '业务板块', '研发负责人', '项目描述',
    '立项时间', '当前阶段', '最新进展', '进度百分比', '是否终止',
    '项目研发质量得分', '项目销售质量得分',
    '客户编码', '客户公司全称', '终端主机厂', '业务负责人',
    '制件名称', '产品代码/零件号', '制件用途', '制件颜色',
    '研发高可落地性项目', '业务高可落地性项目',
    '目标成本 (元/kg)', '竞品售价 (元/kg)', '预估市场订单用量 (吨/年)',
    '计划第一次客户送样时间', '计划第一次客户小试时间', '计划第一次小试完成周期 (天)',
    '计划中试进行时间', '计划量产进行时间', '档案最后更新',
    '项目协同成员', '项目协同成员占比', '销售协同成员', '销售协同成员占比',
    '成品SAP码', '材料牌号', '材料类型',
)

_STAGE_INDEX = {code: index for index, (code, _label) in enumerate(ProjectStage.choices)}


class _NodeColumn:
    def __init__(self, key, header):
        self.key = key
        self.header = header


def build_project_export():
    """返回 xlsx 字节。workbook 和缓冲区在返回前关闭，调用方不要留着它们。"""
    try:
        import openpyxl
        from openpyxl.styles import Alignment
    except ImportError as exc:
        raise ImportError('缺少 openpyxl，无法写入 xlsx') from exc

    workbook = openpyxl.Workbook()
    buffer = BytesIO()
    try:
        worksheet = workbook.active
        worksheet.title = '项目'
        projects = list(_projects())
        columns = _node_columns(projects)
        worksheet.append(list(BASE_HEADERS) + [column.header for column in columns])
        for project in projects:
            worksheet.append(_base_row(project) + _node_cells(project, columns))
        _layout_sheet(worksheet, Alignment)
        workbook.save(buffer)
        return buffer.getvalue()
    finally:
        workbook.close()
        buffer.close()


def _projects():
    return Project.objects.select_related(
        'manager', 'grade', 'business_segment', 'material', 'material__category',
        'repository', 'repository__customer', 'repository__salesperson', 'repository__oem',
    ).prefetch_related(
        'nodes__failure_reason', 'nodes__feedback_type',
        'members__user', 'sales_members__user',
    ).order_by('code')


def _base_row(project):
    repo = getattr(project, 'repository', None)
    material = project.material
    customer = repo.customer if repo and repo.customer_id else None
    oem = repo.oem if repo and repo.oem_id else None
    created = timezone.localtime(project.created_at).strftime('%Y-%m-%d %H:%M:%S')
    updated = timezone.localtime(repo.updated_at).strftime('%Y-%m-%d %H:%M:%S') if repo else ''
    members = _ordered(project.members.all())
    sales_members = _ordered(project.sales_members.all())
    return [
        project.code,
        project.name,
        project.grade.name if project.grade_id else '',
        project.business_segment.name if project.business_segment_id else '',
        _person_label(project.manager),
        project.description,
        created,
        project.get_current_stage_display(),
        project.latest_remark,
        project.progress_percent,
        '是' if project.is_terminated else '否',
        _decimal_text(project.quality_score),
        _decimal_text(project.sales_quality_score),
        customer.customer_code if customer else '',
        customer.company_name if customer else '',
        oem.name if oem else '',
        _person_label(repo.salesperson) if repo else '',
        repo.product_name if repo else '',
        repo.product_code if repo else '',
        repo.part_usage if repo else '',
        repo.part_color if repo else '',
        '是' if repo and repo.rd_high_feasibility else '否',
        '是' if repo and repo.biz_high_feasibility else '否',
        _decimal_text(repo.target_cost) if repo else '',
        _decimal_text(repo.competitor_price) if repo else '',
        _decimal_text(repo.estimated_order_volume) if repo else '',
        _date_text(repo.first_sample_date) if repo else '',
        _date_text(repo.first_trial_date) if repo else '',
        repo.first_trial_cycle_days if repo and repo.first_trial_cycle_days is not None else '',
        _date_text(repo.pilot_date) if repo else '',
        _date_text(repo.mass_production_date) if repo else '',
        updated,
        _names(members),
        _shares(members),
        _names(sales_members),
        _shares(sales_members),
        material.sap_material_code if material else '',
        material.grade_name if material else '',
        material.category.name if material else '',
    ]


def _node_columns(projects):
    columns = {}
    for project in projects:
        for node, extra in _tagged_nodes(project):
            key = _slot_key(node, extra)
            columns.setdefault(key, _header(node, extra))
    return [_NodeColumn(key, header) for key, header in sorted(columns.items())]


def _node_cells(project, columns):
    by_key = {
        _slot_key(node, extra): _node_text(node)
        for node, extra in _tagged_nodes(project)
    }
    return [by_key.get(column.key, '') for column in columns]


def _tagged_nodes(project):
    seen = set()
    for node in sorted(project.nodes.all(), key=lambda item: (item.order, item.pk)):
        pair = (node.stage, node.round)
        extra = pair in seen
        seen.add(pair)
        yield node, extra


def _slot_key(node, extra):
    stage_index = _STAGE_INDEX.get(node.stage, len(_STAGE_INDEX))
    if not extra:
        return (stage_index, node.round, 0, 0)
    return (stage_index, node.round, node.order, node.pk)


def _header(node, extra):
    if not extra:
        return _node_title(node)
    return f'{node.get_stage_display()}（第{node.round}轮·排序{node.order}）'


def _node_title(node):
    return f'{node.get_stage_display()}（第{node.round}轮）'


def _node_text(node):
    lines = [
        _node_title(node),
        f'状态：{node.get_status_display()}',
        f'备注：{node.remark or ""}',
    ]
    if node.failure_reason_id:
        lines.append(f'不合格原因：{node.failure_reason.name}')
    if node.feedback_type_id:
        lines.append(f'客户意见类型：{node.feedback_type.name}')
    if node.updated_at:
        updated = timezone.localtime(node.updated_at).strftime('%Y-%m-%d %H:%M:%S')
        lines.append(f'更新：{updated}')
    return '\n'.join(lines)


# 节点列太窄时，换行会把每一句再折成多行，整行行高被撑开。
_NODE_WIDTH_MIN = 36
_NODE_WIDTH_MAX = 52
_TEXT_WIDTH_MAX = 48
_WIDTH_PADDING = 2


def _layout_sheet(worksheet, alignment_cls):
    node_start = len(BASE_HEADERS) + 1
    wrap = alignment_cls(wrap_text=True, vertical='top')
    top = alignment_cls(vertical='top', wrap_text=False)
    for index, column in enumerate(
        worksheet.iter_cols(min_row=1, max_row=worksheet.max_row), start=1,
    ):
        is_node = index >= node_start
        header_width = _text_width(column[0].value) + _WIDTH_PADDING
        content_width = header_width
        has_break = False
        for cell in column[1:]:
            content_width = max(content_width, _text_width(cell.value) + _WIDTH_PADDING)
            if cell.value and '\n' in str(cell.value):
                has_break = True
        if is_node:
            width = min(max(content_width, _NODE_WIDTH_MIN), max(_NODE_WIDTH_MAX, header_width))
        else:
            width = min(content_width, max(_TEXT_WIDTH_MAX, header_width))
        worksheet.column_dimensions[column[0].column_letter].width = width
        alignment = wrap if is_node or has_break or content_width > width else top
        for cell in column[1:]:
            if cell.value:
                cell.alignment = alignment


def _text_width(value):
    """按 Excel 列宽粗算：中文算 2，英文算 1，多行只取最长一行。"""
    text = '' if value is None else str(value)
    longest = 0
    for line in text.splitlines() or ('',):
        width = sum(2 if ord(char) > 127 else 1 for char in line)
        if width > longest:
            longest = width
    return longest


def _ordered(members):
    return sorted(members, key=lambda member: member.pk)


def _names(members):
    return '、'.join(label for label in (_person_label(member.user) for member in members) if label)


def _shares(members):
    return '、'.join(_share_text(member.workload_share) for member in members)


def _person_label(user):
    if user is None:
        return ''
    full = (user.get_full_name() or '').strip()
    return full or user.username


def _decimal_text(value):
    if value is None:
        return ''
    return format(value, 'f')


def _share_text(value):
    if value is None:
        return ''
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return f'{text}%'


def _date_text(value):
    if value is None:
        return ''
    return value.isoformat()
