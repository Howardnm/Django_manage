"""
种子命令：创建产品报价需求单的 BPMN 流程定义、组织角色、枚举选项。

用法：
    python manage.py seed_quotation

幂等：get_or_create，可重复执行。
"""

from django.core.management.base import BaseCommand

from app_user.models import OrgRole
from app_workflow.models import WorkflowDefinition

from app_quotation.models import ChoiceOption, QuotationField
from app_quotation.services import (
    TASK_BASE_FINANCE,
    TASK_COST,
    TASK_CUSTOMER_PRICE,
    TASK_DEPT_MANAGER,
    TASK_FINANCE_MANAGER,
    TASK_GENERAL_MANAGER,
    TASK_PLANT_DIRECTOR,
    TASK_PURCHASE_PRICE,
    TASK_RD_MANAGER,
    TASK_RD_SELECT,
    TASK_SELECT_BOM,
    TASK_UPLOAD_CONTRACT,
)

# (task_id, 名称, 是否 ServiceTask) — ①发起报价由 startEvent 承载
_FLOW_NODES = [
    (TASK_SELECT_BOM, '选多BOM', False),
    (TASK_PURCHASE_PRICE, '采购填行情价', False),
    (TASK_COST, '边际成本', False),
    (TASK_RD_SELECT, '研发组长选BOM', False),
    (TASK_RD_MANAGER, '研发经理审批', False),
    (TASK_CUSTOMER_PRICE, '客户报价', False),
    (TASK_FINANCE_MANAGER, '财务经理审批', False),
    # ⑨ 成本中心各组组长知会：由 task_completed 信号触发通知（不落 BPMN 节点，ServiceTask 无法序列化）
    (TASK_DEPT_MANAGER, '部门经理审批', False),
    (TASK_PLANT_DIRECTOR, '基地厂长审批', False),
    (TASK_GENERAL_MANAGER, '总经理审批', False),
    (TASK_UPLOAD_CONTRACT, '上传合同', False),
    (TASK_BASE_FINANCE, '基地财务审批', False),
]

# 组织角色 (code, name, scope)
_ORG_ROLES = [
    ('project_clerk', '项目管理专员', OrgRole.Scope.DEPARTMENT),
    ('purchase_specialist', '采购员', OrgRole.Scope.DEPARTMENT),
    ('cost_leader', '成本组长', OrgRole.Scope.WORKGROUP),
    ('group_leader', '组长', OrgRole.Scope.WORKGROUP),
    ('dept_manager', '部门经理', OrgRole.Scope.DEPARTMENT),
    ('finance_manager', '财务经理', OrgRole.Scope.SUBSIDIARY),
    ('plant_director', '基地厂长', OrgRole.Scope.SUBSIDIARY),
    ('general_manager', '总经理', OrgRole.Scope.SUBSIDIARY),
    ('base_finance', '基地财务', OrgRole.Scope.SUBSIDIARY),
]

# 分区标题（发起表单按此分段渲染）
G_BASIC = '基本信息'
G_PACKING = '台板与包装'
G_OTHER_PACK = '其他包装要求'
G_DELIVERY = '运输与交付'
G_PRICE = '价格信息'
G_REMARK = '备注'

# 字段定义 (key, label, field_type, hint, group, order, required, default)
# 除 FK（产品/客户/业务组别/所属公司/业务员）外，基本信息全部由本表驱动。
# 布尔值以「是/否」下拉呈现，默认值 NO。
_FIELDS = [
    # ── 基本申请信息 ──
    ('pricing_mode', '定价模式', 'select', '如：每单议价', G_BASIC, 1, False, ''),
    ('pricing_reason', '定价原因', 'select', '如：正式订单报价', G_BASIC, 2, False, ''),
    ('order_quantity', '订单量（吨）', 'number', '本次订单数量，单位：吨', G_BASIC, 3, False, ''),
    ('customer_category', '客户类别', 'select', '如：一般客户', G_BASIC, 4, False, ''),
    ('settlement_method', '结算方式', 'select', '如：月结30天电汇', G_BASIC, 5, False, ''),
    ('product_spec', '产品规格', 'select', '根据SAP自动带出，可手动调整', G_BASIC, 6, False, ''),
    ('processing_mode', '加工模式', 'select', '如：包工包料', G_BASIC, 7, False, ''),
    # ── 台板与包装 ──
    ('standard_plate_size', '常规台板尺寸', 'select', '如：散包出货', G_PACKING, 8, False, ''),
    ('special_plate_size', '特殊台板尺寸', 'select', '无特殊要求选「/」', G_PACKING, 9, False, ''),
    ('standard_packing', '常规包装', 'select', '如：有字包装袋 25KG/包', G_PACKING, 10, False, ''),
    ('special_packing', '特殊包装', 'select', '无特殊要求选「/」', G_PACKING, 11, False, ''),
    # ── 其他包装要求（布尔 → 是/否 下拉，默认否）──
    ('wrap_film', '缠膜', 'select', '', G_OTHER_PACK, 12, False, 'NO'),
    ('inner_bag', '加内膜袋', 'select', '', G_OTHER_PACK, 13, False, 'NO'),
    ('strapping', '打扎带', 'select', '', G_OTHER_PACK, 14, False, 'NO'),
    ('foil_bag', '铝箔袋', 'select', '', G_OTHER_PACK, 15, False, 'NO'),
    # ── 运输与交付 ──
    ('delivery_region', '收货地区（详细到镇）', 'text', '填文本，如：泰国林查班港口CIF', G_DELIVERY, 16, False, ''),
    ('transport_method', '运输方式', 'text', '填文本，如：包送', G_DELIVERY, 17, False, ''),
    ('odor_control', '气味管控要求', 'select', '', G_DELIVERY, 18, False, 'NO'),
    # ── 价格信息 ──
    ('last_order_price', '上一批订单成交价格（含税元/吨）', 'number', '填数字，无则留空', G_PRICE, 19, False, ''),
    ('last_quote_date', '上一批核价日期', 'date', '填日期，无则留空', G_PRICE, 20, False, ''),
    ('customer_target_price', '客户目标价/元', 'number', '填数字', G_PRICE, 21, False, ''),
    ('target_price_tax', '目标价含税', 'select', '客户目标价是否含税', G_PRICE, 22, False, ''),
    # ── 备注 ──
    ('remark', '备注', 'text', '填文本，如：常规包装，散包装柜', G_REMARK, 23, False, ''),
]

_YES_NO = [('YES', '是'), ('NO', '否')]

# 字段选项 {field_key: [(code, label), ...]}（示例值，可在 admin 增减）
_FIELD_OPTIONS = {
    'pricing_mode': [('PER_ORDER', '每单议价'), ('ANNUAL', '年度框架价'), ('MARKET', '市场价联动')],
    'pricing_reason': [('FORMAL', '正式订单报价'), ('SAMPLE', '打样报价'),
                       ('INQUIRY', '客户询价'), ('ADJUST', '年度调价')],
    'customer_category': [('NORMAL', '一般客户'), ('KEY', '重点客户'),
                          ('STRATEGIC', '战略客户'), ('NEW', '新客户')],
    'settlement_method': [('T30', '月结30天电汇'), ('T60', '月结60天电汇'),
                          ('PREPAY', '预付款'), ('LC', '信用证'), ('CASH', '现金')],
    'product_spec': [('FILL_PP', '填充PP'), ('REIN_PP', '增强PP'),
                     ('DYE_PP', 'PP染色拉粒'), ('OTHER', '其它')],
    'processing_mode': [('ALL_IN', '包工包料'), ('LABOR_ONLY', '包工不包料'), ('SUPPLIED', '来料加工')],
    'standard_plate_size': [('BULK', '散包出货'), ('PALLET', '托盘出货'), ('TON_BAG', '吨袋出货')],
    'special_plate_size': [('NONE', '/'), ('PALLET', '托盘出货'), ('TON_BAG', '吨袋出货')],
    'standard_packing': [('BAG25_PRINT', '有字包装袋 25KG/包'), ('BAG25_PLAIN', '无字包装袋 25KG/包'),
                         ('TON500', '500KG吨袋'), ('BULK', '散装')],
    'special_packing': [('NONE', '/'), ('BAG25_PRINT', '有字包装袋 25KG/包'), ('TON500', '500KG吨袋')],
    'wrap_film': _YES_NO,
    'inner_bag': _YES_NO,
    'strapping': _YES_NO,
    'foil_bag': _YES_NO,
    'odor_control': _YES_NO,
    'target_price_tax': [('INCL', '含税'), ('EXCL', '不含税')],
}

# 早期占位字段（截图确认真实字段后废弃）：只停用不删除，历史快照仍可读
_RETIRED_KEYS = [
    'quote_type', 'payment_terms', 'currency', 'tax_rate', 'transport_terms',
    'packing_terms', 'delivery_terms', 'warranty_terms', 'annual_demand',
    'target_price', 'delivery_date',
]


def _build_bpmn_xml():
    """生成线性 13 节点 BPMN（12 UserTask + 1 ServiceTask）+ 简单纵向 DI。"""
    ns = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" ' \
         'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" ' \
         'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" ' \
         'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" ' \
         'xmlns:camunda="http://camunda.org/schema/1.0/bpmn"'

    parts = [f'<?xml version="1.0" encoding="UTF-8"?>',
             f'<bpmn:definitions {ns} id="Definitions_quotation" '
             f'targetNamespace="http://bpmn.io/schema/bpmn">',
             '<bpmn:process id="quotation_process" name="产品报价需求单流程" isExecutable="true">']

    parts.append('<bpmn:startEvent id="StartEvent" name="发起报价">'
                 '<bpmn:outgoing>Flow_0</bpmn:outgoing></bpmn:startEvent>')

    node_ids = ['StartEvent'] + [n[0] for n in _FLOW_NODES] + ['EndEvent']
    for i, (node_id, name, is_service) in enumerate(_FLOW_NODES):
        tag = 'serviceTask' if is_service else 'userTask'
        incoming = f'<bpmn:incoming>Flow_{i}</bpmn:incoming>'
        outgoing = f'<bpmn:outgoing>Flow_{i + 1}</bpmn:outgoing>'
        parts.append(f'<bpmn:{tag} id="{node_id}" name="{name}">{incoming}{outgoing}</bpmn:{tag}>')

    last = len(_FLOW_NODES)
    parts.append(f'<bpmn:endEvent id="EndEvent" name="完成">'
                 f'<bpmn:incoming>Flow_{last}</bpmn:incoming></bpmn:endEvent>')

    for i in range(last + 1):
        src = node_ids[i]
        tgt = node_ids[i + 1]
        parts.append(f'<bpmn:sequenceFlow id="Flow_{i}" sourceRef="{src}" targetRef="{tgt}" />')

    parts.append('</bpmn:process>')

    # ── 简单纵向 DI（供 bpmn-js 编辑器/查看器渲染）──
    parts.append('<bpmndi:BPMNDiagram id="BPMNDiagram_1">')
    parts.append('<bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="quotation_process">')
    parts.append('<bpmndi:BPMNShape id="StartEvent_di" bpmnElement="StartEvent">'
                 '<dc:Bounds x="180" y="60" width="36" height="36" /></bpmndi:BPMNShape>')
    y = 140
    for node_id, _name, _svc in _FLOW_NODES:
        h = 60 if not _svc else 60
        parts.append(f'<bpmndi:BPMNShape id="{node_id}_di" bpmnElement="{node_id}">'
                     f'<dc:Bounds x="150" y="{y}" width="100" height="{h}" /></bpmndi:BPMNShape>')
        y += 110
    parts.append('<bpmndi:BPMNShape id="EndEvent_di" bpmnElement="EndEvent">'
                 f'<dc:Bounds x="180" y="{y}" width="36" height="36" /></bpmndi:BPMNShape>')

    parts.append('<bpmndi:BPMNEdge id="Flow_0_di" bpmnElement="Flow_0">'
                 '<di:waypoint x="198" y="96" /><di:waypoint x="200" y="140" /></bpmndi:BPMNEdge>')
    y = 140
    for i, (node_id, _name, _svc) in enumerate(_FLOW_NODES):
        y_top = y + 60
        y_next = y_top + 50
        parts.append(f'<bpmndi:BPMNEdge id="Flow_{i + 1}_di" bpmnElement="Flow_{i + 1}">'
                     f'<di:waypoint x="200" y="{y_top}" /><di:waypoint x="200" y="{y_next}" /></bpmndi:BPMNEdge>')
        y += 110
    parts.append('</bpmndi:BPMNPlane></bpmndi:BPMNDiagram>')
    parts.append('</bpmn:definitions>')
    return ''.join(parts)


class Command(BaseCommand):
    help = '创建产品报价需求单的流程定义、组织角色与枚举选项（幂等）'

    def handle(self, *args, **options):
        definition, created = WorkflowDefinition.objects.update_or_create(
            name='产品报价需求单流程',
            defaults={
                'description': '销售核价需求单 14 步审批流（选BOM→行情价→成本→审批）',
                'bpmn_xml': _build_bpmn_xml(),
                'is_active': True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS('已创建流程定义：产品报价需求单流程'))
        else:
            self.stdout.write('流程定义已存在，跳过')

        for code, name, scope in _ORG_ROLES:
            _, created = OrgRole.objects.get_or_create(
                code=code, defaults={'name': name, 'scope': scope})
            if created:
                self.stdout.write(f'  创建组织角色：{code} ({name})')

        for key, label, ftype, hint, group, order, required, default in _FIELDS:
            field, created = QuotationField.objects.update_or_create(
                key=key,
                defaults={'label': label, 'field_type': ftype, 'hint': hint,
                          'group': group, 'order': order, 'required': required,
                          'default_value': default},
            )
            if created:
                self.stdout.write(f'  创建字段定义：{key} ({label})')

            for opt_order, (code, opt_label) in enumerate(_FIELD_OPTIONS.get(key, []), start=1):
                _, created = ChoiceOption.objects.get_or_create(
                    field=field, code=code,
                    defaults={'label': opt_label, 'order': opt_order})
                if created:
                    self.stdout.write(f'  创建选项：{key}.{code} = {opt_label}')

        # 停用早期占位字段（不删除：admin 无删除权限，历史 form_data 快照仍可展示）
        retired = QuotationField.objects.filter(key__in=_RETIRED_KEYS, is_active=True)
        count = retired.update(is_active=False)
        if count:
            self.stdout.write(f'  已停用 {count} 个早期占位字段（数据保留）')

        self.stdout.write(self.style.SUCCESS('seed_quotation 完成。'))
