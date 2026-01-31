from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.db.models import Q
from collections import defaultdict

from app_formula.models import LabFormula, FormulaBOM, FormulaTestResult
from app_repository.models import TestConfig
from app_raw_material.models import RawMaterial

class FormulaChartCompareView(LoginRequiredMixin, TemplateView):
    template_name = 'apps/app_formula/chart_compare.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 1. 从 session 获取已选择的配方 ID
        formula_ids = self.request.session.get('cart_formulas_v2', [])
        
        if not formula_ids:
            context['message'] = "请先从配方列表页选择要对比的配方。"
            return context

        # 2. 获取配方对象
        formulas = LabFormula.objects.filter(pk__in=formula_ids)
        context['formulas'] = formulas
        
        # 3. 提取所有相关的原材料 (BOM)
        bom_lines = FormulaBOM.objects.filter(formula__in=formulas).select_related('raw_material').distinct()
        raw_materials = sorted(list(set(line.raw_material for line in bom_lines)), key=lambda x: x.name)
        context['raw_materials'] = raw_materials

        # 4. 提取所有相关的物性指标
        test_results = FormulaTestResult.objects.filter(formula__in=formulas).select_related('test_config').distinct()
        # 只选择数值类型的指标
        test_configs = sorted(
            list(set(res.test_config for res in test_results if res.test_config.data_type == 'NUMBER')),
            key=lambda x: (x.category.order, x.order)
        )
        context['test_configs'] = test_configs
        
        context['page_title'] = "配方图表对比分析"
        return context


class FormulaChartDataAPI(LoginRequiredMixin, TemplateView):
    
    def get(self, request, *args, **kwargs):
        # 1. 获取请求参数
        x_axis_type = request.GET.get('x_axis_type') # 'raw_material' or 'test_config'
        x_axis_id = request.GET.get('x_axis_id')
        y_axis_type = request.GET.get('y_axis_type') # 'raw_material' or 'test_config'
        y_axis_id = request.GET.get('y_axis_id')
        
        formula_ids = self.request.session.get('cart_formulas_v2', [])

        if not all([x_axis_type, x_axis_id, y_axis_type, y_axis_id, formula_ids]):
            return JsonResponse({'error': '缺少必要的参数 (x_axis, y_axis, formula_ids)'}, status=400)

        # 2. 查询数据
        formulas = LabFormula.objects.filter(pk__in=formula_ids).prefetch_related('bom_lines', 'test_results')
        
        chart_data = []
        
        for f in formulas:
            x_val, y_val = None, None
            
            # 获取 X 轴数据
            if x_axis_type == 'raw_material':
                bom_line = f.bom_lines.filter(raw_material_id=x_axis_id).first()
                x_val = bom_line.percentage if bom_line else 0
            elif x_axis_type == 'test_config':
                test_res = f.test_results.filter(test_config_id=x_axis_id).first()
                x_val = test_res.value if test_res else None

            # 获取 Y 轴数据
            if y_axis_type == 'raw_material':
                bom_line = f.bom_lines.filter(raw_material_id=y_axis_id).first()
                y_val = bom_line.percentage if bom_line else 0
            elif y_axis_type == 'test_config':
                test_res = f.test_results.filter(test_config_id=y_axis_id).first()
                y_val = test_res.value if test_res else None
            
            # 只有当 x 和 y 都有值时才加入数据点
            if x_val is not None and y_val is not None:
                chart_data.append({
                    'x': float(x_val),
                    'y': float(y_val),
                    'name': f.code, # 点的名称
                    'formula_id': f.id
                })

        # 3. 获取坐标轴标题
        x_title, y_title = 'X轴', 'Y轴'
        if x_axis_type == 'raw_material':
            rm = RawMaterial.objects.filter(pk=x_axis_id).first()
            x_title = f"{rm.name} (%)" if rm else 'X轴'
        elif x_axis_type == 'test_config':
            tc = TestConfig.objects.filter(pk=x_axis_id).first()
            x_title = f"{tc.name} ({tc.unit})" if tc else 'X轴'
            
        if y_axis_type == 'raw_material':
            rm = RawMaterial.objects.filter(pk=y_axis_id).first()
            y_title = f"{rm.name} (%)" if rm else 'Y轴'
        elif y_axis_type == 'test_config':
            tc = TestConfig.objects.filter(pk=y_axis_id).first()
            y_title = f"{tc.name} ({tc.unit})" if tc else 'Y轴'

        return JsonResponse({
            'series': [{
                'name': f'{y_title}',
                'data': chart_data,
                'marker': {'radius': 5}
            }],
            'title': {
                'text': f'{x_title} 对 {y_title} 的影响'
            },
            'xAxis': {
                'title': {'text': x_title}
            },
            'yAxis': {
                'title': {'text': y_title}
            }
        })
