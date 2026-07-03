"""
试验工程单打印渲染器。

TrialProductionSheetRenderer:
    将 ProductionOrder 数据转换为匹配「试验工程单.docx」格式的 HTML 打印模板上下文。
    每页最多显示 5 个配方，超出自动分页。

核心思想：renderer 产生一个 pages 列表，每个 page 是自包含的上下文，
模板只需遍历 pages 即可，无需做复杂的列切片。
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from common_utils.printing.base import BasePrintRenderer, PrintConfig
from app_workflow.models import ApprovalHistory
from app_formula.models import AbstractBOMEntry


class TrialProductionSheetRenderer(BasePrintRenderer):
    """试验工程单 — HTML 打印渲染器。

    用法::

        renderer = TrialProductionSheetRenderer(production_order=order)
        html = renderer.render_html()
    """

    template_name = 'apps/app_trial_production/order/print_sheet.html'

    FORMULAS_PER_PAGE = 5

    # ── 喂料口标签映射（来源：AbstractBOMEntry.FEEDING_CHOICES） ──
    # FEEDING_CHOICES 中 label 格式为「主喂料 (Main)」，stripped 后得到
    # 短标签用于打印模板。模型层修改 choices 时此处自动同步。
    PORT_LABELS = {
        val: re.sub(r'\s*\(.*?\)\s*', '', label)
        for val, label in AbstractBOMEntry.FEEDING_CHOICES
    }

    # ── 审批操作常量（来源：ApprovalHistory.ACTION_CHOICES） ──
    # 模型层修改 approval action choices 时需同步检查此处。
    _APPROVE_ACTION = 'APPROVE'

    # 公司 Logo 路径（相对于 static/ 目录）
    COMPANY_LOGO_PATH = 'images/saite.png'

    def __init__(
        self,
        production_order=None,
        config: PrintConfig | None = None,
    ) -> None:
        super().__init__(config)
        self.order = production_order
        self._formulas: list | None = None
        self._details_map: dict | None = None

    # ═══════════════════════════════════════════════════════
    #  公共入口
    # ═══════════════════════════════════════════════════════

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        if self.order is None:
            return {'order': None, 'pages': [], 'error': '未提供工单对象'}

        formulas = self._get_formulas()
        details_map = self._get_details_map()

        # 共享数据
        header_info = self._build_header_info()
        post_processing = self._build_post_processing()
        mold_matrix = self._build_mold_matrix(formulas)
        signatures = self._build_signatures()

        # 按页构建自包含上下文
        formula_groups = self._paginate_formulas(formulas)
        all_formula_indices = list(range(len(formulas)))
        pages = []

        for group in formula_groups:
            # 该组配方在全部配方列表中的 start 索引
            group_start = formulas.index(group[0]) if group else 0
            group_indices = list(range(group_start, group_start + len(group)))

            # 每配方是否需要色粉
            formula_colors = []
            for idx in group_indices:
                fd = details_map.get(formulas[idx].pk)
                formula_colors.append(
                    fd.needs_color_matching if fd else False
                )

            page = {
                'formulas': group,
                'formula_count': len(group),
                'total_cols': 6 + len(group) * 2,
                'bom_rows': self._build_bom_rows_for_group(
                    formulas, details_map, group_indices,
                ),
                'bom_totals': self._calc_totals_for_group(
                    formulas, details_map, group_indices,
                ),
                'formula_colors': formula_colors,
            }
            pages.append(page)

        return {
            'order': self.order,
            'pages': pages,
            'formulas': formulas,
            'header_info': header_info,
            'post_processing': post_processing,
            'mold_matrix': mold_matrix,
            'signatures': signatures,
            'total_pages': len(pages),
            'company_logo_url': self.get_company_logo_url(),
        }

    # ═══════════════════════════════════════════════════════
    #  数据加载
    # ═══════════════════════════════════════════════════════

    def _get_formulas(self) -> list:
        if self._formulas is not None:
            return self._formulas
        from app_formula.models import LabFormula

        self._formulas = list(
            LabFormula.objects.filter(
                code=self.order.trial_code,
                project=self.order.project,
            )
            .prefetch_related('bom_lines__raw_material__category')
            .order_by('version')
        )
        return self._formulas

    def _get_details_map(self) -> dict:
        if self._details_map is not None:
            return self._details_map
        self._details_map = {
            fd.formula_id: fd
            for fd in self.order.formula_details.all()
        }
        return self._details_map

    # ═══════════════════════════════════════════════════════
    #  分页
    # ═══════════════════════════════════════════════════════

    def get_company_logo_url(self) -> str:
        """返回公司 Logo 的静态文件 URL。

        覆盖此方法可动态切换不同子公司的 logo。
        """
        from django.contrib.staticfiles.storage import staticfiles_storage
        return staticfiles_storage.url(self.COMPANY_LOGO_PATH)

    @staticmethod
    def _paginate_formulas(formulas: list) -> list[list]:
        per_page = TrialProductionSheetRenderer.FORMULAS_PER_PAGE
        return [
            formulas[i : i + per_page]
            for i in range(0, len(formulas), per_page)
        ] or [[]]

    # ═══════════════════════════════════════════════════════
    #  头部信息
    # ═══════════════════════════════════════════════════════

    def _build_header_info(self) -> dict[str, Any]:
        order = self.order
        project = order.project
        material = project.material if project else None
        profile = order.process_profile

        # ── 配方颜色字段（取自第一个配方版本）──
        formulas = self._get_formulas()
        first_formula = formulas[0] if formulas else None

        return {
            'order_code': order.code or '',
            'project_name': project.name if project else '',
            'creator_display': self._get_user_display(order.creator),
            'creator_dept_path': self._get_creator_dept_path(order.creator),
            'material_category': (
                material.category.name
                if material and material.category else ''
            ),
            'material_name': material.grade_name if material else '',
            'sap_code': order.sap_material_code or '',
            'created_date': (
                order.created_at.strftime('%Y-%m-%d')
                if order.created_at else ''
            ),
            'customer': self._get_customer_name(),
            'project_stage': (
                order.project_node.get_stage_display()
                if order.project_node else ''
            ),
            'needs_color_display': self._format_needs_color(),
            'material_color_name': (
                first_formula.material_color_name
                if first_formula else ''
            ),
            'pantone_code': (
                first_formula.pantone_code
                if first_formula else ''
            ),
            'rgb_value': (
                first_formula.rgb_value
                if first_formula else ''
            ),
            'has_formula_color': (
                bool(first_formula and (
                    first_formula.material_color_name
                    or first_formula.pantone_code
                    or first_formula.rgb_value
                ))
            ),
            'machine_name': (
                profile.machine.model_name
                if profile and profile.machine else ''
            ),
            'total_planned_qty': float(order.quantity_planned or 0),
        }

    def _get_customer_name(self) -> str:
        """获取客户名称 — 从项目档案的直接客户读取。

        ProjectRepository.project 为 OneToOneField(related_name='repository')。
        View 层已通过 select_related('project__repository__customer') 预加载，
        无 ProjectRepository 时 repo 为 None。
        """
        order = self.order
        project = order.project
        if not project:
            return ''
        # 直接访问 OneToOneField 反向关系，related_name 变更时此处将引发
        # AttributeError，确保模型层修改能被及时发现。
        repo = project.repository
        if repo is not None and repo.customer_id is not None:
            return str(repo.customer)
        return ''

    def _get_creator_dept_path(self, user) -> str:
        """构建创建人的部门/工作组全路径。

        由于 Department 是扁平结构（无父子层级），路径格式为：
            「部门名」或「部门名 / 工作组名」

        User.department → FK(Department)；User.work_groups → WorkGroup M2M 反向。
        """
        if not user:
            return ''
        parts = []
        # department 是 User 模型实际 FK 字段，直接访问
        if user.department_id is not None:
            parts.append(user.department.name)
        # work_groups 是 WorkGroup 的 related_name，取用户的主要工作组（第一个）
        wgs = list(user.work_groups.select_related('department')[:1])
        if wgs:
            parts.append(wgs[0].name)
        return ' / '.join(parts) if parts else ''

    def _format_needs_color(self) -> str:
        details_map = self._get_details_map()
        if not details_map:
            return ''
        has_color = any(
            fd.needs_color_matching for fd in details_map.values()
        )
        no_color = any(
            not fd.needs_color_matching for fd in details_map.values()
        )
        if has_color and not no_color:
            return '是'
        if no_color and not has_color:
            return '否'
        if has_color and no_color:
            return '部分'
        return ''

    # ═══════════════════════════════════════════════════════
    #  BOM 表构建（核心）
    # ═══════════════════════════════════════════════════════

    def _build_bom_rows_for_group(
        self,
        formulas: list,
        details_map: dict,
        group_indices: list[int],
    ) -> list[dict[str, Any]]:
        """为一个配方组（一页）构建扁平 BOM 行数据。

        每行自带 feeding_port_label，不再使用全宽 section header。
        """
        if not formulas:
            return []

        rows = []
        base_formula = formulas[0]

        row_index = 0
        for base_line in base_formula.bom_lines.all().order_by(
            'feeding_port', 'weighing_scale',
            'raw_material__category__order', 'raw_material__name',
        ):
            raw_id = base_line.raw_material_id
            raw_material = base_line.raw_material
            feeding_port = base_line.feeding_port

            # 仅构建本组配方索引对应的列
            formula_data = []
            for idx in group_indices:
                f = formulas[idx]
                pct = Decimal('0')
                for bl in f.bom_lines.all():
                    if (
                        bl.raw_material_id == raw_id
                        and bl.feeding_port == feeding_port
                    ):
                        pct = bl.percentage
                        break
                fd = details_map.get(f.pk)
                planned_qty = float(fd.planned_quantity) if fd else 0
                pct_val = float(pct) if pct else 0
                feeding_qty = (
                    round((pct_val / 100.0) * planned_qty, 3)
                    if planned_qty > 0 else 0.0
                )
                formula_data.append({
                    'pct': pct_val if pct_val else '',
                    'qty': feeding_qty,
                })

            # 构建备注信息（共混 / 分秤 / 回掺）
            notes_parts = []
            if base_line.is_pre_mix:
                notes_parts.append(
                    f'共混{base_line.pre_mix_order}'
                    f'({base_line.pre_mix_time}s)'
                )
            if base_line.weighing_scale:
                notes_parts.append(
                    base_line.get_weighing_scale_display()
                )
            if base_line.is_tail:
                notes_parts.append('尾料回掺')

            row_index += 1
            rows.append({
                'row_index': row_index,
                'feeding_port_label': self.PORT_LABELS.get(feeding_port, feeding_port),
                'sap_code': raw_material.warehouse_code or '',
                'material_name': raw_material.name,
                'material_model': raw_material.model_name or '',
                'weighing_scale': (
                    base_line.get_weighing_scale_display()
                    if base_line.weighing_scale else ''
                ),
                'notes': '；'.join(notes_parts) if notes_parts else '',
                'formula_data': formula_data,
            })
        return rows

    def _calc_totals_for_group(
        self,
        formulas: list,
        details_map: dict,
        group_indices: list[int],
    ) -> list[dict[str, Any]]:
        """计算本组每个配方的投料量合计。"""
        totals = []
        for idx in group_indices:
            f = formulas[idx]
            fd = details_map.get(f.pk)
            planned_qty = float(fd.planned_quantity) if fd else 0
            row_total = Decimal('0')
            pct_total = Decimal('0')
            for bl in f.bom_lines.all():
                pct_val = float(bl.percentage) if bl.percentage else 0
                pct_total += Decimal(str(pct_val))
                qty = (pct_val / 100.0) * planned_qty if planned_qty > 0 else 0
                row_total += Decimal(str(round(qty, 3)))
            totals.append({
                'version': f.version,
                'pct_total': round(float(pct_total), 1),
                'kg_total': round(float(row_total), 3),
                'planned_qty': planned_qty,
            })
        return totals

    # ═══════════════════════════════════════════════════════
    #  后处理信息
    # ═══════════════════════════════════════════════════════

    def _build_post_processing(self) -> dict[str, Any]:
        order = self.order
        profile = order.process_profile

        return {
            'profile_name': profile.name if profile else '',
            'profile_machine': (
                profile.machine.model_name
                if profile and profile.machine else ''
            ),
            'profile_screw': (
                profile.screw_combination.name
                if profile and profile.screw_combination else ''
            ),
            'drying_temperature': (
                f'{order.drying_temperature}℃'
                if order.drying_temperature else ''
            ),
            'drying_duration': (
                f'{order.drying_duration}h'
                if order.drying_duration else ''
            ),
            'inner_bag_sealing': '是' if order.inner_bag_sealing else '',
            'injection_temperature': (
                f'{order.injection_temperature}℃'
                if order.injection_temperature else ''
            ),
            'injection_pretreatment': order.injection_pretreatment or '',
            'packaging_desc': order.packaging_desc or '',
            'storage_location': order.storage_location or '',
            'remark': order.remark or '',
        }

    # ═══════════════════════════════════════════════════════
    #  注塑模具需求矩阵
    # ═══════════════════════════════════════════════════════

    def _build_mold_matrix(self, formulas: list) -> dict[str, Any] | None:
        order = self.order
        mold_reqs = list(
            order.mold_requirements.filter(injection_task__isnull=True)
            .select_related('mold')
            .prefetch_related('formula_details')
            .order_by('order', 'pk')
        )
        # InjectionTask.production_order 为 OneToOneField(related_name='injection_task')，
        # 无注塑任务时 getattr 返回 None。
        injection_task = getattr(order, 'injection_task', None)
        if not mold_reqs and injection_task is not None:
            mold_reqs = list(
                injection_task.mold_requirements
                .select_related('mold')
                .prefetch_related('formula_details')
                .order_by('order', 'pk')
            )

        if not mold_reqs:
            return None

        mold_rows = []
        formula_totals = [0] * len(formulas)
        grand_total = 0

        for mr in mold_reqs:
            mold = mr.mold
            qty_map = {
                d.formula_id: d.specimen_quantity
                for d in mr.formula_details.all()
            }
            cells = []
            row_total = 0
            for i, f in enumerate(formulas):
                qty = qty_map.get(f.pk, 0) or 0
                cells.append({'qty': qty})
                row_total += qty
                formula_totals[i] += qty
            grand_total += row_total
            mold_rows.append({
                'mold_name': mold.name,
                'mold_code': mold.mold_code,
                'standard': mold.get_standard_display(),
                'cavity_count': mold.cavity_count,
                'cells': cells,
                'row_total': row_total,
            })

        return {
            'mold_rows': mold_rows,
            'formulas': formulas,
            'formula_totals': formula_totals,
            'grand_total': grand_total,
        }

    # ═══════════════════════════════════════════════════════
    #  签章区
    # ═══════════════════════════════════════════════════════

    @staticmethod
    def _get_user_display(user) -> str:
        """安全获取用户显示名。

        优先级：full_name → username。
        User.get_full_name() 来自 Django AbstractUser 基类。
        """
        if not user:
            return ''
        full_name = user.get_full_name()
        return full_name or user.username

    def _build_signatures(self) -> dict[str, Any]:
        order = self.order
        wi = order.workflow_instance

        # 编制人
        prepared_by = self._get_user_display(order.creator)

        # 审批记录：仅 APPROVE 操作，按时间排序
        approvals = []
        if wi:
            for h in wi.history.filter(action=self._APPROVE_ACTION).select_related('approver').order_by('timestamp'):
                approvals.append({
                    'name': self._get_user_display(h.approver),
                    'date': h.timestamp.strftime('%Y-%m-%d %H:%M') if h.timestamp else '',
                })

        return {
            'prepared_by': prepared_by,
            'prepared_date': (
                order.created_at.strftime('%Y-%m-%d %H:%M')
                if order.created_at else ''
            ),
            'approvals': approvals,
        }
