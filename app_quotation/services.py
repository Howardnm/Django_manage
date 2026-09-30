"""
产品报价需求单业务编排层。

职责：
  - 审批人解析（按任务 ID + 需求单累积状态，供 task_created 信号处理器调用）
  - 启动/推进审批流（复用 app_workflow.WorkflowService，不改 app_workflow）
  - BOM 成本核算（复用 app_formula 成本内核，价格源换成行情价）
  - 行情价写入（QuotationMaterialPrice → 不可变 RawMaterialMarketPrice）

关键复用：
  - app_formula/services/cost_service.weighted_unit_cost — 纯算术内核，与价格来源无关。
  - app_workflow/resolver.OrgRoleResolver — 按发起人 org 解析角色（带逐级回退）。
"""

import logging
from decimal import Decimal

from django.db import transaction

from app_workflow.resolver import OrgRoleResolver

from .models import QuotationBOM, QuotationMaterialPrice, QuotationRequest

logger = logging.getLogger(__name__)


# ── 流程任务 ID（与 seed 的 BPMN userTask id 一一对应）─────────────
# 注：① 发起报价 由创建页直接完成（startEvent），不落为 UserTask。
TASK_SELECT_BOM = 'Task_select_bom'        # ② 项目管理专员选多BOM（可移交研发工程师）
TASK_PURCHASE_PRICE = 'Task_purchase_price'  # ③ 采购填写行情价
TASK_COST = 'Task_cost'                    # ④ 成本专员填边际成本/贡献率
TASK_RD_SELECT = 'Task_rd_select'          # ⑤ 研发组长选一个BOM提交
TASK_RD_MANAGER = 'Task_rd_manager'        # ⑥ 研发经理审批
TASK_CUSTOMER_PRICE = 'Task_customer_price'  # ⑦ 业务组别工作组组长填客户报价
TASK_FINANCE_MANAGER = 'Task_finance_manager'  # ⑧ 财务经理审批
# ⑨ 成本中心各组组长知会（ServiceTask，自动通过，无审批人）
TASK_DEPT_MANAGER = 'Task_dept_manager'    # ⑩ 业务组别部门经理审批
TASK_PLANT_DIRECTOR = 'Task_plant_director'  # ⑪ 基地厂长审批
TASK_GENERAL_MANAGER = 'Task_general_manager'  # ⑫ 总经理审批
TASK_UPLOAD_CONTRACT = 'Task_upload_contract'  # ⑬ 发起人上传合同附件
TASK_BASE_FINANCE = 'Task_base_finance'    # ⑭ 基地财务审批

# 有序步骤（用于状态展示/推进判断），不含 ServiceTask 知会节点
STEP_TASKS = [
    TASK_SELECT_BOM, TASK_PURCHASE_PRICE, TASK_COST,
    TASK_RD_SELECT, TASK_RD_MANAGER, TASK_CUSTOMER_PRICE, TASK_FINANCE_MANAGER,
    TASK_DEPT_MANAGER, TASK_PLANT_DIRECTOR, TASK_GENERAL_MANAGER,
    TASK_UPLOAD_CONTRACT, TASK_BASE_FINANCE,
]

# 步骤展示名（不含⑨知会 ServiceTask）
STEP_LABELS = {
    TASK_SELECT_BOM: '② 选多BOM',
    TASK_PURCHASE_PRICE: '③ 采购填行情价',
    TASK_COST: '④ 边际成本',
    TASK_RD_SELECT: '⑤ 研发组长选BOM',
    TASK_RD_MANAGER: '⑥ 研发经理审批',
    TASK_CUSTOMER_PRICE: '⑦ 客户报价',
    TASK_FINANCE_MANAGER: '⑧ 财务经理审批',
    TASK_DEPT_MANAGER: '⑩ 部门经理审批',
    TASK_PLANT_DIRECTOR: '⑪ 基地厂长审批',
    TASK_GENERAL_MANAGER: '⑫ 总经理审批',
    TASK_UPLOAD_CONTRACT: '⑬ 上传合同',
    TASK_BASE_FINANCE: '⑭ 基地财务审批',
}

# ── 组织角色编码（seed 命令据此创建 OrgRole）──────────────────────
ROLE_PROJECT_CLERK = 'project_clerk'        # 项目管理专员
ROLE_PURCHASE = 'purchase_specialist'       # 采购员
ROLE_COST_LEADER = 'cost_leader'            # 成本组长
ROLE_GROUP_LEADER = 'group_leader'          # 组长（研发组长 / 业务组组长通用）
ROLE_DEPT_MANAGER = 'dept_manager'          # 部门经理（研发经理 / 业务组部门经理通用）
ROLE_FINANCE_MANAGER = 'finance_manager'    # 财务经理
ROLE_PLANT_DIRECTOR = 'plant_director'      # 基地厂长
ROLE_GENERAL_MANAGER = 'general_manager'    # 总经理
ROLE_BASE_FINANCE = 'base_finance'          # 基地财务


def _resolve_org_role(role_code, *, initiator=None, workgroup=None,
                      department=None, subsidiary=None):
    """按组织角色解析一个用户。

    - initiator 传入时走 OrgRoleResolver（按发起人的 workgroup→department→subsidiary
      逐级回退）；
    - workgroup/department/subsidiary 传入时直接查该组织单元的主负责人
      （用于「选定业务组别/分基地」这类非发起人维度的解析）。
    """
    from app_user.models import OrgRole, OrgRoleAssignment

    if initiator is not None:
        return OrgRoleResolver(initiator=initiator).resolve(role_code)

    role = OrgRole.objects.filter(code=role_code).first()
    if role is None:
        return None
    qs = OrgRoleAssignment.objects.filter(role=role, is_primary=True)
    if workgroup is not None:
        qs = qs.filter(workgroup=workgroup)
    elif department is not None:
        qs = qs.filter(department=department)
    elif subsidiary is not None:
        qs = qs.filter(subsidiary=subsidiary)
    else:
        return None
    assignment = qs.first()
    return assignment.user if assignment else None


def _bom_assignee(request):
    """②选多BOM 步骤的最终经办人（项目管理专员或移交后的研发工程师）。"""
    if not request.workflow_instance_id:
        return None
    task = request.workflow_instance.tasks.filter(
        spiff_task_id=TASK_SELECT_BOM,
    ).order_by('-completed_at').first()
    return task.assigned_to if task else None


def resolve_assignee(request, task_id):
    """按任务 ID + 需求单状态解析审批人，返回 User 或 None。"""
    if task_id == TASK_UPLOAD_CONTRACT:
        return request.creator
    if task_id == TASK_SELECT_BOM:
        return _resolve_org_role(ROLE_PROJECT_CLERK, initiator=request.creator)
    if task_id == TASK_PURCHASE_PRICE:
        return _resolve_org_role(ROLE_PURCHASE, initiator=request.creator)
    if task_id == TASK_COST:
        return _resolve_org_role(ROLE_COST_LEADER, initiator=request.creator)
    if task_id == TASK_RD_SELECT:
        return _resolve_org_role(ROLE_GROUP_LEADER, initiator=_bom_assignee(request))
    if task_id == TASK_RD_MANAGER:
        return _resolve_org_role(ROLE_DEPT_MANAGER, initiator=_bom_assignee(request))
    if task_id == TASK_CUSTOMER_PRICE:
        return _resolve_org_role(ROLE_GROUP_LEADER, workgroup=request.business_group)
    if task_id == TASK_FINANCE_MANAGER:
        return _resolve_org_role(ROLE_FINANCE_MANAGER, initiator=request.creator)
    if task_id == TASK_DEPT_MANAGER:
        return _resolve_org_role(ROLE_DEPT_MANAGER, department=request.business_group.department)
    if task_id == TASK_PLANT_DIRECTOR:
        return _resolve_org_role(ROLE_PLANT_DIRECTOR, subsidiary=request.subsidiary)
    if task_id == TASK_GENERAL_MANAGER:
        return _resolve_org_role(ROLE_GENERAL_MANAGER, initiator=request.creator)
    if task_id == TASK_BASE_FINANCE:
        return _resolve_org_role(ROLE_BASE_FINANCE, subsidiary=request.subsidiary)
    return None


class QuotationService:
    """产品报价需求单服务门面。"""

    # ── 流程启动 ──────────────────────────────────────────────

    @staticmethod
    def start_flow(request: QuotationRequest, definition):
        """启动 14 步审批流，绑定回调。返回 WorkflowInstance。"""
        from app_workflow.services import WorkflowService

        callback_config = {
            'handler': 'app_quotation.workflow_handlers.handle_quotation_callback',
            'args': {'request_pk': request.pk},
        }
        with transaction.atomic():
            instance = WorkflowService.start(
                definition=definition,
                started_by=request.creator,
                related_object=request,
                context_data={},
                callback_config=callback_config,
            )
            request.workflow_instance = instance
            request.status = QuotationRequest.Status.RUNNING
            request.save(update_fields=['workflow_instance', 'status'])
        return instance

    @staticmethod
    def get_workflow_definition():
        """查找报价需求单的 BPMN 流程定义（seed 按「产品报价」命名创建）。"""
        from app_workflow.models import WorkflowDefinition
        return (WorkflowDefinition.objects
                .filter(is_active=True, name__icontains='产品报价')
                .order_by('-id').first())

    # ── 候选配方 ──────────────────────────────────────────────

    @staticmethod
    def candidate_formulas(finished_material):
        """成品关联的所有项目的所有配方（步骤②选多BOM 数据源）。"""
        from app_formula.models import LabFormula
        return LabFormula.objects.filter(
            project__material=finished_material,
        ).select_related('project', 'material_type', 'creator')

    @staticmethod
    def _build_matrix(formulas):
        """由配方列表构建对比矩阵：列=配方，行=原材料并集，单元格=比例。

        Returns (columns, rows)，columns 与入参 formulas 同序。
        """
        formulas = list(formulas)
        if not formulas:
            return [], []
        columns = [{'formula': f} for f in formulas]
        all_raw = set()
        pct_map = {}
        for f in formulas:
            pct_map[f.pk] = {}
            for line in f.bom_lines.all():  # 只用 .all()：select_related 会丢 prefetch 缓存
                all_raw.add(line.raw_material)
                pct_map[f.pk][line.raw_material_id] = line.percentage

        sorted_rm = sorted(all_raw, key=lambda x: (x.category.order, x.name))
        rows = []
        for rm in sorted_rm:
            values = []
            for f in formulas:
                pct = pct_map[f.pk].get(rm.pk)
                values.append({'percentage': pct})  # None 表示该配方不含此料
            rows.append({'raw_material': rm, 'values': values})
        return columns, rows

    @staticmethod
    def bom_matrix(finished_material):
        """候选配方 BOM 对比矩阵（步骤②选BOM数据源，全部候选）。"""
        from app_formula.models import LabFormula
        formulas = LabFormula.objects.filter(project__material=finished_material) \
            .select_related('project', 'material_type') \
            .prefetch_related('bom_lines__raw_material__category')
        return QuotationService._build_matrix(formulas)

    @staticmethod
    def selected_bom_matrix(request: QuotationRequest):
        """只读矩阵：仅展示步骤②已复选的配方（QuotationBOM）。"""
        boms = list(request.boms.select_related('formula')
                    .prefetch_related('formula__bom_lines__raw_material__category')
                    .order_by('pk'))
        return QuotationService._build_matrix([b.formula for b in boms])

    @staticmethod
    def is_bom_matrix_viewer(request: QuotationRequest, user):
        """选BOM审批人 / 成本中心审批人 / 超管 是否始终可见 BOM 对比矩阵。

        选BOM最终经办人含「移交研发工程师」后的经办人（_bom_assignee 取最新任务 assigned_to）；
        成本中心审批人按发起人 org 实时解析（cost_leader 成本组长）。
        """
        if user.is_superuser:
            return True
        if not request.workflow_instance_id:
            return False
        # 选BOM最终经办人（含移交）
        bom_user = _bom_assignee(request)
        if bom_user and bom_user.pk == user.pk:
            return True
        # 成本中心审批人（成本组长）
        cost_user = resolve_assignee(request, TASK_COST)
        if cost_user and cost_user.pk == user.pk:
            return True
        return False

    # ── 成本核算（复用 app_formula 内核，价格源换成行情价）────────

    @staticmethod
    def bom_cost(bom: QuotationBOM):
        """单个候选配方的含税成本 = Σ(比例 × 含税行情价) / Σ比例。

        任一非 0% 的行缺价 → 返回 None（严格模式，与 cost_service 一致）。
        """
        from app_formula.services.cost_service import weighted_unit_cost

        request = bom.request
        prices = {
            mp.raw_material_id: mp.price_tax_included
            for mp in request.material_prices.all()
        }

        def price_of(line):
            return prices.get(line.raw_material_id)

        return weighted_unit_cost(bom.formula.bom_lines.all(), price_of)

    @staticmethod
    def bom_cost_map(request: QuotationRequest):
        """批量计算需求单所有候选配方的成本，返回 {bom_pk: Decimal|None}。"""
        boms = list(request.boms.select_related('formula').prefetch_related(
            'formula__bom_lines__raw_material'))
        return {bom.pk: QuotationService.bom_cost(bom) for bom in boms}

    @staticmethod
    def material_lines(request: QuotationRequest):
        """步骤③采购填价的数据源：候选 BOM 涉及的原材料并集（去重），不含比例。

        返回 [{raw_material, warehouse_code, name, model_name,
               existing_price, latest_price}]。
        """
        raw_material_ids = set()
        for bom in request.boms.prefetch_related('formula__bom_lines'):
            for line in bom.formula.bom_lines.all():
                raw_material_ids.add(line.raw_material_id)
        if not raw_material_ids:
            return []

        from app_raw_material.models import RawMaterial
        existing = {mp.raw_material_id: mp for mp in request.material_prices.all()}
        lines = []
        for rm in (RawMaterial.objects.filter(pk__in=raw_material_ids)
                   .order_by('category', 'name')):
            latest = QuotationService.latest_market_price(rm)
            ex = existing.get(rm.pk)
            lines.append({
                'raw_material': rm,
                'warehouse_code': rm.warehouse_code,
                'name': rm.name,
                'model_name': rm.model_name,
                'existing_price': ex.price_tax_included if ex else None,
                'latest_price': latest,
            })
        return lines

    # ── 行情价写入（只增不改）─────────────────────────────────

    @staticmethod
    def latest_market_price(raw_material):
        """某原材料的最新含税行情价（用于采购预填），无记录返回 None。"""
        from app_raw_material.models import RawMaterialMarketPrice
        record = (RawMaterialMarketPrice.objects
                  .filter(raw_material=raw_material)
                  .order_by('-entered_at').first())
        return record.price_tax_included if record else None

    @staticmethod
    def write_market_prices(request: QuotationRequest, user):
        """把需求单的行情价明细固化到不可变历史模型。

        每次采购提交行情价都新增一条 RawMaterialMarketPrice（含需求单号/时间/录入人），
        旧需求单的价格不受影响。返回写入的历史记录条数。
        """
        from app_raw_material.models import RawMaterialMarketPrice
        from django.utils import timezone

        written = 0
        for mp in request.material_prices.select_related('raw_material'):
            RawMaterialMarketPrice.objects.create(
                raw_material=mp.raw_material,
                price_tax_included=mp.price_tax_included,
                tax_rate=mp.tax_rate,
                price_tax_excluded=(mp.price_tax_included / (1 + mp.tax_rate)).quantize(Decimal('0.01')),
                price_date=timezone.now().date(),
                entered_by=user,
                entered_by_name=user.get_full_name() or user.username,
                source_request_no=request.code,
                source_request_id=request.pk,
            )
            written += 1
        return written
