from django.contrib import messages
from django.urls import reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect
from django.db.models import Subquery, OuterRef, DecimalField, Q

from app_formula.models import LabFormula, FormulaTestResult
from app_formula.forms import LabFormulaForm, FormulaBOMFormSet, FormulaTestResultFormSet
from app_formula.utils.filters import LabFormulaFilter
from app_formula.mixins import FormulaAccessMixin


class LabFormulaListView(FormulaAccessMixin, ListView):
    """
    实验配方列表：
    - 准入：app_formula.view_labformula + 研发/管理员身份。
    - 隔离：仅限本部门配方。
    """
    permission_required = 'app_formula.view_labformula'
    model = LabFormula
    template_name = 'apps/app_formula/list.html'
    context_object_name = 'formulas'
    paginate_by = 20

    def get_queryset(self):
        # 1. 调用 Mixin 自动执行部门隔离过滤
        base_qs = super().get_queryset().select_related(
            'material_type', 'creator', 'process'
        ).prefetch_related('related_materials', 'research_projects')
        
        # 2. 动态指标排序逻辑 (保持原有功能)
        sort_params = self.request.GET.getlist('sort')
        metric_map = {
            'density': ('密度', 'val_density'),
            'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融', 'val_melt'),
            'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'),
            'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'),
            'hdt': ('热变形', 'val_hdt'),
        }

        # 4. 动态 Annotate
        if sort_params:
            std = self.request.GET.get('std', 'ISO')
            for param in sort_params:
                clean_sort = param.lstrip('-')
                if clean_sort in metric_map:
                    keyword, field_name = metric_map[clean_sort]
                    base_qs = base_qs.annotate(**{
                        field_name: Subquery(
                            FormulaTestResult.objects.filter(
                                formula=OuterRef('pk'),
                                test_config__name__icontains=keyword,
                                test_config__standard__icontains=std
                            ).values('value')[:1],
                            output_field=DecimalField()
                        )
                    })

        self.filterset = LabFormulaFilter(self.request.GET, queryset=base_qs, request=self.request)
        return self.filterset.qs.order_by('-created_at') if not sort_params else self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 性能优化：批量加载测试结果 (逻辑保持不变)
        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']

        # 1. 获取当前页的所有配方 ID
        page_formulas = context['formulas'] # 这是一个 list 或 QuerySet
        formula_ids = [f.pk for f in page_formulas]
        
        std_query = Q()
        for k in std_keywords: std_query |= Q(test_config__standard__icontains=k)
        
        results = FormulaTestResult.objects.filter(formula_id__in=formula_ids).filter(
            std_query, 
            test_config__name__regex=r'(密度|灰分|熔融|拉伸|弯曲|冲击|热变形)'
        ).select_related('test_config')
        
        data_map = {}
        for res in results:
            fid = res.formula_id
            if fid not in data_map: data_map[fid] = {}
            name = res.test_config.name
            if '密度' in name: data_map[fid]['val_density'] = res.value
            elif '灰分' in name: data_map[fid]['val_ash'] = res.value
            elif '熔融' in name: data_map[fid]['val_melt'] = res.value
            elif '拉伸' in name: data_map[fid]['val_tensile'] = res.value
            elif '弯曲强度' in name: data_map[fid]['val_flex_strength'] = res.value
            elif '弯曲模量' in name: data_map[fid]['val_flex_modulus'] = res.value
            elif '冲击' in name: data_map[fid]['val_impact'] = res.value
            elif '热变形' in name: data_map[fid]['val_hdt'] = res.value

        # 4. 将数据挂载到配方对象上
        for f in page_formulas:
            if f.pk in data_map:
                for key, val in data_map[f.pk].items(): setattr(f, key, val)

        context.update({
            'cart_formula_ids': self.request.session.get('cart_formulas_v2', []),
            'filter': self.filterset,
            'current_std': current_std,
            'current_sort': self.request.GET.get('sort', ''),
        })
        return context


class LabFormulaDetailView(FormulaAccessMixin, DetailView):
    """配方详情：需有查看权限，且仅限本部门。"""
    permission_required = 'app_formula.view_labformula'
    model = LabFormula
    template_name = 'apps/app_formula/detail.html'
    context_object_name = 'formula'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_object_permission(obj) # 拦截跨部门访问
        return obj

    def get_queryset(self):
        return super().get_queryset().select_related('material_type', 'creator', 'process').prefetch_related(
            'bom_lines__raw_material',
            'test_results__test_config',
            'related_materials',
            'research_projects'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sorted_results = self.object.test_results.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        context['sorted_test_results'] = sorted_results
        return context


class LabFormulaCreateView(FormulaAccessMixin, CreateView):
    """创建配方：需有增加权限，且通常仅限研发。"""
    permission_required = 'app_formula.add_labformula'
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    # 处理预关联材料
    def get_initial(self):
        initial = super().get_initial()
        material_id = self.request.GET.get('material_id')
        if material_id: initial['related_materials'] = [material_id]
        project_id = self.request.GET.get('research_project_id')
        if project_id: initial['research_projects'] = [project_id]
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增实验配方'
        if self.request.POST:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, prefix='test')
        else:
            # 预留 6 行空表单
            FormulaBOMFormSet.extra = 6
            FormulaTestResultFormSet.extra = 9
            context['bom_formset'] = FormulaBOMFormSet(prefix='bom', queryset=LabFormula.objects.none())
            context['test_formset'] = FormulaTestResultFormSet(prefix='test', queryset=LabFormula.objects.none())
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        bom_formset = context['bom_formset']
        test_formset = context['test_formset']
        with transaction.atomic():
            form.instance.creator = self.request.user
            self.object = form.save()
            if bom_formset.is_valid() and test_formset.is_valid():
                bom_formset.instance = self.object
                bom_formset.save()
                test_formset.instance = self.object
                test_formset.save()
                self.object.calculate_cost() # 自动计算成本
            else:
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, "配方已创建")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('formula_detail', kwargs={'pk': self.object.pk})


class LabFormulaUpdateView(FormulaAccessMixin, UpdateView):
    """编辑配方：需有修改权限，且仅限本部门。"""
    permission_required = 'app_formula.change_labformula'
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        self.check_object_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑实验配方'
        if self.request.POST:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, instance=self.object, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, instance=self.object, prefix='test')
        else:
            FormulaBOMFormSet.extra = 1
            FormulaTestResultFormSet.extra = 1
            context['bom_formset'] = FormulaBOMFormSet(instance=self.object, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(instance=self.object, prefix='test')
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        bom_formset = context['bom_formset']
        test_formset = context['test_formset']
        with transaction.atomic():
            self.object = form.save()
            if bom_formset.is_valid() and test_formset.is_valid():
                bom_formset.save()
                test_formset.save()
                self.object.calculate_cost()
            else:
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, "配方已更新")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('formula_detail', kwargs={'pk': self.object.pk})


class LabFormulaDuplicateView(FormulaAccessMixin, UpdateView):
    """
    复制配方：
    - 逻辑：基于现有配方内容创建一个新对象。
    - 权限：需具备 add 权限，且基于原部门配方进行复制。
    """
    permission_required = 'app_formula.add_labformula'
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    def get_object(self, queryset=None):
        # 获取原始配方对象
        original_formula = super().get_object(queryset)
        self.check_object_permission(original_formula) # 只能复制自己部门的
        return original_formula

    # 重新实现为 CreateView 逻辑
    def dispatch(self, request, *args, **kwargs):
        self.original_formula = self.get_object()
        return super().dispatch(request, *args, **kwargs)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '复制配方'

        # 如果是 GET 请求，预填充 FormSet 数据
        if not self.request.POST:
            bom_initial = [{
                'feeding_port': bom.feeding_port, 'weighing_scale': bom.weighing_scale,
                'raw_material': bom.raw_material, 'percentage': bom.percentage,
                'is_tail': bom.is_tail, 'is_pre_mix': bom.is_pre_mix,
                'pre_mix_order': bom.pre_mix_order, 'pre_mix_time': bom.pre_mix_time,
            } for bom in self.original_formula.bom_lines.all()]
            context['bom_formset'] = FormulaBOMFormSet(prefix='bom', initial=bom_initial)
            # 关键：设置 extra 为列表长度，以显示所有初始数据
            context['bom_formset'].extra = len(bom_initial)
            
            test_initial = [{
                'test_config': res.test_config, 'value': res.value,
                'test_date': res.test_date, 'remark': res.remark,
            } for res in self.original_formula.test_results.all()]
            context['test_formset'] = FormulaTestResultFormSet(prefix='test', initial=test_initial)
            context['test_formset'].extra = len(test_initial)
        else:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, prefix='test')
        return context

    def get_initial(self):
        initial = super().get_initial()
        # 预填充主表单数据
        initial.update({
            'name': f"{self.original_formula.name} (副本)",
            'material_type': self.original_formula.material_type,
            'process': self.original_formula.process,
            'cost_actual': self.original_formula.cost_actual,
            'description': self.original_formula.description,
            'related_materials': self.original_formula.related_materials.all(),
            'research_projects': self.original_formula.research_projects.all()
        })
        return initial

    def form_valid(self, form):
        context = self.get_context_data()
        bom_formset = context['bom_formset']
        test_formset = context['test_formset']
        with transaction.atomic():
            form.instance.pk = None 
            form.instance.code = None 
            form.instance.creator = self.request.user
            self.object = form.save()
            if bom_formset.is_valid() and test_formset.is_valid():
                bom_formset.instance = self.object
                bom_formset.save()
                test_formset.instance = self.object
                test_formset.save()
                self.object.calculate_cost()
            else:
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, "配方已复制并创建")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('formula_detail', kwargs={'pk': self.object.pk})
