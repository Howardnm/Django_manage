import json
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
        
        formula_ids = self.request.session.get('cart_formulas_v2', [])
        
        if not formula_ids:
            context['message'] = "请先从配方列表页选择要对比的配方。"
            return context

        formulas = LabFormula.objects.filter(pk__in=formula_ids)
        context['formulas'] = formulas
        
        bom_lines = FormulaBOM.objects.filter(formula__in=formulas).select_related('raw_material', 'raw_material__category').distinct()
        raw_materials = sorted(list(set(line.raw_material for line in bom_lines)), key=lambda x: (x.category.order, x.name))
        context['raw_materials'] = raw_materials

        test_results = FormulaTestResult.objects.filter(formula__in=formulas).select_related('test_config', 'test_config__category').distinct()
        test_configs = sorted(
            list(set(res.test_config for res in test_results if res.test_config.data_type == 'NUMBER')),
            key=lambda x: (x.category.order, x.order)
        )
        context['test_configs'] = test_configs
        
        context['page_title'] = "配方图表对比分析"
        return context


class FormulaChartDataAPI(LoginRequiredMixin, TemplateView):
    
    def get(self, request, *args, **kwargs):
        x_axis_type = request.GET.get('x_axis_type')
        x_axis_id = request.GET.get('x_axis_id')
        y_axes_str = request.GET.get('y_axes')
        
        formula_ids = self.request.session.get('cart_formulas_v2', [])

        if not all([x_axis_type, x_axis_id, y_axes_str, formula_ids]):
            return JsonResponse({'error': '缺少必要的参数 (x_axis, y_axes, formula_ids)'}, status=400)

        try:
            y_axes = json.loads(y_axes_str)
            if not isinstance(y_axes, list) or not y_axes:
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Y轴参数格式错误'}, status=400)

        formulas = LabFormula.objects.filter(pk__in=formula_ids).prefetch_related('bom_lines', 'test_results')
        
        series_data = []
        y_axis_configs = []

        # --- X轴标题 ---
        x_title_text = 'X轴'
        if x_axis_type == 'raw_material':
            rm = RawMaterial.objects.select_related('category').filter(pk=x_axis_id).first()
            if rm:
                x_title_text = f"({rm.category.name}){rm.name}{f' {rm.model_name}' if rm.model_name else ''} (%)"
        elif x_axis_type == 'test_config':
            tc = TestConfig.objects.filter(pk=x_axis_id).first()
            if tc:
                x_title_text = f"{tc.name}{f' ({tc.condition})' if tc.condition else ''} ({tc.unit})"

        # --- 循环处理每个Y轴 ---
        for i, y_axis in enumerate(y_axes):
            y_axis_type = y_axis.get('type')
            y_axis_id = y_axis.get('id')
            
            current_series_data = []
            
            for f in formulas:
                x_val, y_val = None, None
                
                if x_axis_type == 'raw_material':
                    bom_line = f.bom_lines.filter(raw_material_id=x_axis_id).first()
                    x_val = bom_line.percentage if bom_line else 0
                elif x_axis_type == 'test_config':
                    test_res = f.test_results.filter(test_config_id=x_axis_id).first()
                    x_val = test_res.value if test_res else None

                if y_axis_type == 'raw_material':
                    bom_line = f.bom_lines.filter(raw_material_id=y_axis_id).first()
                    y_val = bom_line.percentage if bom_line else 0
                elif y_axis_type == 'test_config':
                    test_res = f.test_results.filter(test_config_id=y_axis_id).first()
                    y_val = test_res.value if test_res else None
                
                if x_val is not None and y_val is not None:
                    current_series_data.append({
                        'x': float(x_val),
                        'y': float(y_val),
                        'name': f.code,
                        'formula_id': f.id
                    })
            
            y_title_text = f'Y轴{i+1}'
            y_unit = ''
            if y_axis_type == 'raw_material':
                rm = RawMaterial.objects.select_related('category').filter(pk=y_axis_id).first()
                if rm:
                    y_title_text = f"({rm.category.name}){rm.name}{f' {rm.model_name}' if rm.model_name else ''} (%)"
                y_unit = '%'
            elif y_axis_type == 'test_config':
                tc = TestConfig.objects.filter(pk=y_axis_id).first()
                if tc:
                    y_title_text = f"{tc.name}{f' ({tc.condition})' if tc.condition else ''} ({tc.unit})"
                    y_unit = tc.unit
            
            series_data.append({
                'name': y_title_text,
                'data': current_series_data,
                'type': 'spline',
                'yAxis': i,
                'tooltip': { 'valueSuffix': f' {y_unit}' }
            })
            
            y_axis_configs.append({
                'title': {'text': y_title_text},
                'opposite': i % 2 != 0
            })

        return JsonResponse({
            'series': series_data,
            'title': { 'text': None },
            'xAxis': { 'title': {'text': x_title_text} },
            'yAxis': y_axis_configs
        })
