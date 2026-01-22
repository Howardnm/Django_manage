from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect
from django.db.models import Subquery, OuterRef, FloatField, DecimalField, Q

from app_formula.models import LabFormula, FormulaTestResult
from app_formula.forms import LabFormulaForm, FormulaBOMFormSet, FormulaTestResultFormSet
from app_formula.utils.filters import LabFormulaFilter
from app_repository.models import MaterialLibrary

class LabFormulaListView(LoginRequiredMixin, ListView):
    model = LabFormula
    template_name = 'apps/app_formula/list.html'
    context_object_name = 'formulas'
    paginate_by = 20

    def get_queryset(self):
        # 1. 基础查询
        qs = super().get_queryset().select_related('material_type', 'creator', 'process').prefetch_related('related_materials')
        
        # 2. 获取排序参数 (支持多个)
        sort_params = self.request.GET.getlist('sort')
        
        # 3. 映射表
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
                    
                    qs = qs.annotate(**{
                        field_name: Subquery(
                            FormulaTestResult.objects.filter(
                                formula=OuterRef('pk'),
                                test_config__name__icontains=keyword,
                                test_config__standard__icontains=std
                            ).values('value')[:1],
                            output_field=DecimalField()
                        )
                    })

        # 【修复】传入 request 参数，以便 FilterSet 内部可以访问 self.request
        self.filterset = LabFormulaFilter(self.request.GET, queryset=qs, request=self.request)
        
        # 5. 默认排序
        if not sort_params:
            return self.filterset.qs.order_by('-created_at')
            
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 【性能优化】内存填充数据 (仅处理当前页)
        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
        
        # 1. 获取当前页的所有配方 ID
        page_formulas = context['formulas'] # 这是一个 list 或 QuerySet
        formula_ids = [f.pk for f in page_formulas]
        
        # 2. 一次性查出所有相关的测试结果
        key_keywords = ['密度', '灰分', '熔融', '拉伸', '弯曲', '冲击', '热变形']
        
        # 构建标准查询
        std_query = Q()
        for k in std_keywords:
            std_query |= Q(test_config__standard__icontains=k)
            
        # 构建指标名查询
        name_query = Q()
        for k in key_keywords:
            name_query |= Q(test_config__name__icontains=k)
            
        results = FormulaTestResult.objects.filter(
            formula_id__in=formula_ids
        ).filter(std_query & name_query).select_related('test_config')
        
        # 3. 构建数据字典
        data_map = {}
        for res in results:
            fid = res.formula_id
            if fid not in data_map: data_map[fid] = {}
            
            name = res.test_config.name
            val = res.value
            
            if '密度' in name: data_map[fid]['val_density'] = val
            elif '灰分' in name: data_map[fid]['val_ash'] = val
            elif '熔融' in name: data_map[fid]['val_melt'] = val
            elif '拉伸' and '强度' in name: data_map[fid]['val_tensile'] = val
            elif '弯曲' and '强度' in name: data_map[fid]['val_flex_strength'] = val
            elif '弯曲' and '模量' in name: data_map[fid]['val_flex_modulus'] = val
            elif '冲击' in name: data_map[fid]['val_impact'] = val
            elif '热变形' in name: data_map[fid]['val_hdt'] = val

        # 4. 将数据挂载到配方对象上
        for f in page_formulas:
            if f.pk in data_map:
                for key, val in data_map[f.pk].items():
                    setattr(f, key, val)

        context['filter'] = self.filterset
        context['current_std'] = current_std
        context['current_sort'] = self.request.GET.get('sort', '') 
        return context

class LabFormulaDetailView(LoginRequiredMixin, DetailView):
    model = LabFormula
    template_name = 'apps/app_formula/detail.html'
    context_object_name = 'formula'

    def get_queryset(self):
        # 【修改】预加载 test_results 时，按 TestConfig 的 order 排序
        return super().get_queryset().select_related('material_type', 'creator', 'process').prefetch_related(
            'bom_lines__raw_material', 
            'test_results__test_config',
            'test_results__test_config__category', # 预加载分类
            'related_materials'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 【新增】手动对 test_results 进行排序
        # 因为 prefetch_related 的排序能力有限，或者需要在 Python 中二次处理
        # 这里我们获取关联的 test_results 并按 category__order 和 order 排序
        sorted_results = self.object.test_results.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 
            'test_config__order'
        )
        context['sorted_test_results'] = sorted_results
        return context

class LabFormulaCreateView(LoginRequiredMixin, CreateView):
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    # 【新增】处理预关联材料
    def get_initial(self):
        initial = super().get_initial()
        material_id = self.request.GET.get('material_id')
        if material_id:
            # 注意：对于多对多字段，initial 应该是一个列表
            initial['related_materials'] = [material_id]
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增实验配方'
        if self.request.POST:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, prefix='test')
        else:
            # 【修改】预留 6 行空表单
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
                
                # 自动计算成本
                self.object.calculate_cost()
            else:
                return self.render_to_response(self.get_context_data(form=form))
                
        messages.success(self.request, "配方已创建")
        # 【修复】使用 self.object.pk 而不是 self.object.id，确保兼容性
        # 并且确保 redirect 使用的是 get_success_url 返回的 URL 字符串
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('formula_detail', kwargs={'pk': self.object.pk})

class LabFormulaUpdateView(LoginRequiredMixin, UpdateView):
    model = LabFormula
    form_class = LabFormulaForm
    template_name = 'apps/app_formula/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑实验配方'
        if self.request.POST:
            context['bom_formset'] = FormulaBOMFormSet(self.request.POST, instance=self.object, prefix='bom')
            context['test_formset'] = FormulaTestResultFormSet(self.request.POST, instance=self.object, prefix='test')
        else:
            # 【修改】编辑时，如果已有数据少于6行，补足到6行
            # 注意：inlineformset_factory 的 extra 默认是 3，这里我们动态调整
            # 但为了简单起见，这里只设置 extra=1 (方便添加)，或者保持默认
            # 如果要强制显示6行空行，逻辑会比较复杂，通常编辑模式下按需添加更好
            # 这里我们保持默认行为，或者稍微增加一点 extra
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
                
                # 自动计算成本
                self.object.calculate_cost()
            else:
                return self.render_to_response(self.get_context_data(form=form))
                
        messages.success(self.request, "配方已更新")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('formula_detail', kwargs={'pk': self.object.pk})
