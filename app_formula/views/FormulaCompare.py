from django.views.generic import TemplateView, View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from app_material.models import MaterialLibrary
from app_formula.models import LabFormula
from app_formula.mixins import FormulaAccessMixin
from app_raw_material.models import RawMaterial, PriceAvgConfig
from common_utils.comparison_matrix import build_compare_matrices
from common_utils.serializers.compare import serialize_compare
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
import json

# ==========================================
# 1. 对比购物车 API
# ==========================================
class FormulaCompareCartView(FormulaAccessMixin, View):
    """
    处理对比列表的增删改查 (基于 Session)
    Session Key: 'cart_formulas_v2' -> [id1, id2, ...] (V2版本，彻底隔离)
    Session Key: 'cart_materials_v2' -> [id1, id2, ...]
    Session Key: 'cart_raw_materials_v2' -> [id1, id2, ...] (新增：原材料)

    准入：仅研发工程师 + 管理员（RND_ONLY）。
    非研发用户不会在 header 中看到购物车组件，因此不会触发 AJAX 403。
    """
    permission_required = 'app_formula.view_labformula'
    model = LabFormula

    def get(self, request):
        """获取当前对比列表"""
        formula_ids = request.session.get('cart_formulas_v2', [])
        material_ids = request.session.get('cart_materials_v2', [])
        raw_material_ids = request.session.get('cart_raw_materials_v2', [])

        formulas = self.get_queryset().filter(pk__in=formula_ids).values('id', 'code', 'name')
        materials = MaterialLibrary.objects.filter(pk__in=material_ids).values('id', 'grade_name', 'manufacturer')
        raw_materials = RawMaterial.objects.filter(pk__in=raw_material_ids).values('id', 'name', 'model_name', 'supplier__name')
        
        # 统一格式返回
        items = []
        for f in formulas:
            items.append({'id': f['id'], 'name': f['code'], 'desc': f['name'], 'type': 'formula'})
        for m in materials:
            items.append({'id': m['id'], 'name': m['grade_name'], 'desc': m['manufacturer'], 'type': 'material'})
        for rm in raw_materials:
            desc = rm['supplier__name'] if rm['supplier__name'] else ''
            name = f"{rm['name']} {rm['model_name']}" if rm['model_name'] else rm['name']
            items.append({'id': rm['id'], 'name': name, 'desc': desc, 'type': 'raw_material'})
            
        return JsonResponse({'count': len(items), 'items': items})

    def post(self, request):
        """加入/移除对比"""
        action = request.POST.get('action') # 'add', 'remove', 'clear', 'toggle', 'add_multiple'
        item_type = request.POST.get('type') # 'formula' or 'material' or 'raw_material'

        # 【严格检查】必须指定 type，且必须合法
        if action != 'clear' and item_type not in ['formula', 'material', 'raw_material']:
            return JsonResponse({'status': 'error', 'message': 'Invalid type parameter'}, status=400)

        # 使用 list() 创建副本，防止引用问题
        formula_ids = list(request.session.get('cart_formulas_v2', []))
        material_ids = list(request.session.get('cart_materials_v2', []))
        raw_material_ids = list(request.session.get('cart_raw_materials_v2', []))
        
        # 确定目标列表
        if item_type == 'material':
            target_list = material_ids
        elif item_type == 'raw_material':
            target_list = raw_material_ids
        else:
            target_list = formula_ids
        
        if action == 'clear':
            # 清空所有
            formula_ids = []
            material_ids = []
            raw_material_ids = []
            target_list = [] # 重置引用
            
        elif action == 'add_multiple':
            # 批量添加
            ids_str = request.POST.get('ids') # JSON string or comma separated
            if ids_str:
                try:
                    # 尝试解析 JSON 列表
                    new_ids = json.loads(ids_str)
                    if not isinstance(new_ids, list):
                        new_ids = [int(ids_str)]
                except:
                    # 尝试解析逗号分隔
                    new_ids = [int(x) for x in ids_str.split(',') if x.isdigit()]
                
                for fid in new_ids:
                    try:
                        fid_int = int(fid)
                        if fid_int not in target_list:
                            if item_type == 'formula' and not self.get_queryset().filter(pk=fid_int).exists():
                                continue
                            target_list.append(fid_int)
                    except (ValueError, TypeError):
                        continue
                        
        else:
            # 单个操作
            item_id = request.POST.get('id')
            if item_id:
                try:
                    fid = int(item_id)
                    if action == 'add':
                        if fid not in target_list:
                            if item_type == 'formula' and not self.get_queryset().filter(pk=fid).exists():
                                return JsonResponse({'status': 'error', 'message': '配方不存在或无权访问'}, status=403)
                            target_list.append(fid)
                    elif action == 'remove':
                        if fid in target_list:
                            target_list.remove(fid)
                    elif action == 'toggle':
                        if fid in target_list:
                            target_list.remove(fid)
                        else:
                            if item_type == 'formula' and not self.get_queryset().filter(pk=fid).exists():
                                return JsonResponse({'status': 'error', 'message': '配方不存在或无权访问'}, status=403)
                            target_list.append(fid)
                except ValueError:
                    pass
        
        # 更新 Session
        if action == 'clear':
            request.session['cart_formulas_v2'] = []
            request.session['cart_materials_v2'] = []
            request.session['cart_raw_materials_v2'] = []
        else:
            if item_type == 'material':
                request.session['cart_materials_v2'] = target_list
            elif item_type == 'raw_material':
                request.session['cart_raw_materials_v2'] = target_list
            elif item_type == 'formula':
                request.session['cart_formulas_v2'] = target_list
            
        total_count = len(request.session.get('cart_formulas_v2', [])) + \
                      len(request.session.get('cart_materials_v2', [])) + \
                      len(request.session.get('cart_raw_materials_v2', []))
        
        return JsonResponse({
            'status': 'success', 
            'count': total_count, 
            'ids': target_list,
            'type': item_type
        })


# ==========================================
# 2. 对比页面视图
# ==========================================
class FormulaCompareView(FormulaAccessMixin, TemplateView):
    permission_required = 'app_formula.view_labformula'
    model = LabFormula
    template_name = 'apps/app_formula/compare.html'

    def post(self, request, *args, **kwargs):
        # 检查是否是导出请求
        if 'export_excel' in request.POST:
            return self.export_excel(request)
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 1. 获取参数
        # 支持 POST (表单提交) 和 GET (URL参数)
        if self.request.method == 'POST':
            material_id = self.request.POST.get('material_id') # 单个基准材料 (旧逻辑兼容)
            # 过滤空值，防止 [''] 导致 int 转换错误
            formula_ids = [x for x in self.request.POST.getlist('formula_ids') if x]
            material_ids = [x for x in self.request.POST.getlist('material_ids') if x]
            raw_material_ids = [x for x in self.request.POST.getlist('raw_material_ids') if x]

            # 如果完全没传参数，回退到 Session
            if not formula_ids and not material_ids and not raw_material_ids and not material_id:
                formula_ids = self.request.session.get('cart_formulas_v2', [])
                material_ids = self.request.session.get('cart_materials_v2', [])
                raw_material_ids = self.request.session.get('cart_raw_materials_v2', [])

        else:
            material_id = self.request.GET.get('material_id')
            formula_ids = self.request.GET.getlist('ids') # 优先从 URL 获取 ids (旧逻辑兼容)
            material_ids = self.request.GET.getlist('m_ids')
            raw_material_ids = self.request.GET.getlist('rm_ids')
            
            # 如果 URL 没参数，从 Session 获取
            if not formula_ids and not material_ids and not raw_material_ids and not material_id:
                formula_ids = self.request.session.get('cart_formulas_v2', [])
                material_ids = self.request.session.get('cart_materials_v2', [])
                raw_material_ids = self.request.session.get('cart_raw_materials_v2', [])

        # 2. 获取对象 — 配方走 get_queryset() 确保 L4 部门隔离
        formulas = list(self.get_queryset().filter(pk__in=formula_ids)
            .select_related('creator', 'material_type', 'project', 'process')
            .prefetch_related('bom_lines__raw_material__category',
                              'test_results__test_config__category',
                              'color_powder_bom__entries__raw_material__category')
            .order_by('created_at'))
        materials = list(MaterialLibrary.objects.filter(pk__in=material_ids)
            .prefetch_related('properties__test_config__category')
            .order_by('created_at'))
        raw_materials = list(RawMaterial.objects.filter(pk__in=raw_material_ids)
            .prefetch_related('properties__test_config__category')
            .order_by('created_at'))
        
        # 兼容旧的单基准材料逻辑
        base_material = None
        if material_id:
            base_material = get_object_or_404(MaterialLibrary, pk=material_id)
            # 如果基准材料不在列表里，加进去作为第一列
            if base_material not in materials:
                materials.insert(0, base_material)
        
        if not formulas and not materials and not raw_materials:
             messages.warning(self.request, "请先选择要对比的项目")
             return context

        # 3. 定义列头 (混合排序或分组)
        # 策略：先放材料，再放原材料，再放配方
        columns = []
        for m in materials:
            columns.append({'type': 'material', 'obj': m})
        for rm in raw_materials:
            columns.append({'type': 'raw_material', 'obj': rm})
        for f in formulas:
            columns.append({'type': 'formula', 'obj': f})

        # 4. 构建 BOM / 色粉BOM / 性能 对比矩阵（共享矩阵构建器）
        bom_matrix, cpbom_matrix, test_matrix = build_compare_matrices(columns)

        context['columns'] = columns
        context['bom_matrix'] = bom_matrix
        context['cpbom_matrix'] = cpbom_matrix
        context['test_matrix'] = test_matrix
        avg_months = PriceAvgConfig.get().months
        context['avg_months'] = avg_months
        context['compare_data'] = serialize_compare(
            columns, (bom_matrix, cpbom_matrix, test_matrix), avg_months, None,
        )
        context['page_title'] = "综合对比分析"
        # 传递 material 对象以便模板兼容旧逻辑 (如果有且仅有一个材料且在第一位)
        if materials and len(materials) == 1 and columns[0]['type'] == 'material':
            context['material'] = materials[0]
        
        return context

    # 分区 → Excel 分区标题行的配色（与页面对比表的 section color 对应）
    _SECTION_FILL = {
        'orange': ('FFF5E6', 'FFA500'),
        'pink': ('FCE7F3', 'DB2777'),
        'purple': ('F3E5F5', '800080'),
        'cyan': ('E0F7FA', '00838F'),
        'green': ('E8F5E9', '2E7D32'),
        'blue': ('E3F2FD', '1565C0'),
    }

    # 这些分区的值应写成数值单元格（可求和）；其余按文本原样写
    _NUMERIC_SECTIONS = {'cost', 'avg_price', 'cp_cost', 'total_cost', 'bom', 'cpbom', 'performance'}

    @staticmethod
    def _num(value):
        """把 _fmt() 出来的展示字符串反解回数值，保住 Excel 的数值类型。

        直接写字符串会让单元格变成文本，财务/采购无法求和 —— 这是最容易漏的回归。
        空值（'-'）写成空单元格；非数字文本（如测试结论「合格」）原样写回。
        """
        if value is None or value == '-':
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    def export_excel(self, request):
        """导出 Excel 报表。

        直接由 compare_data 渲染 —— 与页面消费同一份序列化结果，
        由构造保证「页面显示什么，Excel 就是什么」（原先 Excel 自行用
        property 重算，且漏了色粉成本行，两边口径会分叉）。
        """
        context = self.get_context_data()
        if not context or 'columns' not in context:
            return redirect('formula_list')

        columns = context['columns']
        compare_data = context.get('compare_data')
        if not compare_data:
            return redirect('formula_list')

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "对比报表"

        # 样式
        header_font = Font(bold=True, size=12)
        header_fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
        left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)
        border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        red_font = Font(color="FF0000", bold=True)
        green_font = Font(color="008000", bold=True)

        # 1. 表头
        headers = ["分类 / 项目", "详情 / 标准", "单位"]
        for col in columns:
            if col['type'] == 'material':
                headers.append(f"材料\n{col['obj'].grade_name}")
            elif col['type'] == 'raw_material':
                name = f"{col['obj'].name} {col['obj'].model_name}" if col['obj'].model_name else col['obj'].name
                headers.append(f"原材料\n{name}")
            else:
                headers.append(f"配方\n{col['obj'].code}\n{col['obj'].name}")
        ws.append(headers)

        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_align
            cell.border = border

        # 2. 各分区 —— 与页面完全同源
        for section in compare_data['sections']:
            if section['band']:
                ws.append([section['label']])
                ws.merge_cells(start_row=ws.max_row, start_column=1,
                               end_row=ws.max_row, end_column=len(headers))
                fill_color, font_color = self._SECTION_FILL.get(
                    section['color'], ('F0F0F0', '000000'))
                title_cell = ws.cell(row=ws.max_row, column=1)
                title_cell.fill = PatternFill(
                    start_color=fill_color, end_color=fill_color, fill_type='solid')
                title_cell.font = Font(color=font_color, bold=True)

            to_cell = (self._num if section['key'] in self._NUMERIC_SECTIONS
                       else (lambda v: v))
            for row in section['rows']:
                ws.append([row['label'], row['label2'], row['unit']]
                          + [to_cell(v['v']) for v in row['values']])
                current_row_idx = ws.max_row
                # 性能分区的涨跌色（列偏移 3：前 3 列是固定列）
                for i, value in enumerate(row['values']):
                    if value['cls'] == 'text-green':
                        ws.cell(row=current_row_idx, column=i + 4).font = green_font
                    elif value['cls'] == 'text-red':
                        ws.cell(row=current_row_idx, column=i + 4).font = red_font

        # 样式调整
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = center_align
                cell.border = border
                if cell.column == 1 or cell.column == 2:  # 前两列左对齐
                    cell.alignment = left_align

        ws.column_dimensions['A'].width = 20  # 分类/项目
        ws.column_dimensions['B'].width = 30  # 详情/标准
        ws.column_dimensions['C'].width = 10  # 单位
        for i in range(4, len(headers) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 20

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        filename = "综合对比报表.xlsx"
        # 处理中文文件名
        from django.utils.encoding import escape_uri_path
        response['Content-Disposition'] = f'attachment; filename="{escape_uri_path(filename)}"'

        wb.save(response)
        return response
