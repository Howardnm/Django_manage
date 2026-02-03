from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, FloatField, DecimalField
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_repository.forms import MaterialForm, MaterialDataFormSet, MaterialFileForm
from app_repository.models import MaterialLibrary, MaterialDataPoint, MaterialFile
from app_repository.utils.filters import MaterialFilter
from app_formula.models import FormulaTestResult # 引入配方测试结果模型


# ==========================================
# 2. 材料库视图 (Material)
# ==========================================

# --- 列表视图 (含 Tab 切换逻辑) ---
class MaterialListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_repository.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_repository/material/material_list.html'
    context_object_name = 'materials'
    paginate_by = 10

    def get_queryset(self):
        # 1. 基础查询：只预加载关联表，不通过 SQL 计算数值
        qs = super().get_queryset() \
            .select_related('category') \
            .prefetch_related('scenarios', 'properties', 'properties__test_config')

        # 2. 获取当前排序参数
        sort_param = self.request.GET.get('sort', '')

        # 3. 【核心修复】映射表修改
        # Key: URL参数名 (对应 filters.py 里的右边参数)
        # Value: (中文指标关键词, 数据库annotate字段名)
        metric_map = {
            'density': ('密度', 'val_density'),
            'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融指数', 'val_melt'),
            'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'),
            'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'),  # 这里注意 filters.py 里写的 key 是什么
            'hdt': ('变形温度', 'val_hdt'),  # 这里做个简化，只取一个 HDT 排序
            # 如果 filters.py 里写的是 'hdt', 这里 key 就是 'hdt'
        }

        # 检查是否需要排序
        if sort_param:
            # 去掉可能的负号 (倒序)
            clean_sort = sort_param.lstrip('-')

            # 如果排序字段在我们的映射表中，就动态添加该字段的子查询
            if clean_sort in metric_map:
                keyword, field_name = metric_map[clean_sort]

                # 获取当前标准 (ISO/ASTM)
                current_std = self.request.GET.get('std', 'ISO')
                std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']

                # 动态构建查询
                from django.db.models import Q
                std_query = Q()
                for k in std_keywords:
                    std_query |= Q(test_config__standard__icontains=k)

                # 【修复】使用正确的 field_name 进行 annotate
                qs = qs.annotate(**{
                    field_name: Subquery(
                        MaterialDataPoint.objects.filter(
                            std_query,
                            material=OuterRef('pk'),
                            test_config__name__icontains=keyword
                        ).order_by('-id').values('value')[:1],
                        output_field=DecimalField()
                    )
                })

        # 4. 接入过滤器
        # 【修复】传入 request 参数，以便 FilterSet 内部可以访问 self.request
        self.filterset = MaterialFilter(self.request.GET, queryset=qs, request=self.request)

        # 5. 默认排序
        if not sort_param:
            return self.filterset.qs.order_by('-created_at')

        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Python 内存填充数据 (逻辑不变，保持高效展示)
        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']

        for mat in context['materials']:
            props = mat.properties.all()

            def find_val_in_memory(keyword):
                for p in props:
                    if keyword in p.test_config.name:
                        if any(k in p.test_config.standard for k in std_keywords):
                            return p.value
                return None

            # 填充虚拟属性供 Template 使用
            if not hasattr(mat, 'val_density'): mat.val_density = find_val_in_memory("密度")
            if not hasattr(mat, 'val_ash'): mat.val_ash = find_val_in_memory("灰分")
            if not hasattr(mat, 'val_melt'): mat.val_melt = find_val_in_memory("熔融指数")
            if not hasattr(mat, 'val_tensile'): mat.val_tensile = find_val_in_memory("拉伸强度")
            if not hasattr(mat, 'val_flex_strength'): mat.val_flex_strength = find_val_in_memory("弯曲强度")
            if not hasattr(mat, 'val_flex_modulus'): mat.val_flex_modulus = find_val_in_memory("弯曲模量")
            if not hasattr(mat, 'val_impact'): mat.val_impact = find_val_in_memory("冲击")

            # HDT 特殊处理：因为列表显示的是合并列，这里只取一个主要的用于排序显示
            # 实际上列表页 Template 并没有直接用 val_hdt，而是用了 val_hdt 作为排序参考
            if not hasattr(mat, 'val_hdt'): mat.val_hdt = find_val_in_memory("变形温度")

        # 【新增】传递购物车中的材料 ID，用于前端回显勾选状态
        # 使用新的 Session Key: cart_materials_v2
        context['cart_material_ids'] = self.request.session.get('cart_materials_v2', [])

        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        context['current_std'] = current_std
        return context


# --- 创建视图 ---
class MaterialCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_materiallibrary'
    raise_exception = True
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_repository/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST)
        else:
            # 【修改】预留 6 行空表单
            MaterialDataFormSet.extra = 6
            context['data_formset'] = MaterialDataFormSet(queryset=MaterialDataPoint.objects.none())
        context['page_title'] = '录入新材料'
        context['is_edit'] = False
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        data_formset = context['data_formset']
        with transaction.atomic():
            self.object = form.save()
            if data_formset.is_valid():
                data_formset.instance = self.object
                data_formset.save()
            else:
                return self.render_to_response(self.get_context_data(form=form))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('repo_material_detail', kwargs={'pk': self.object.pk})


# --- 更新视图 ---
class MaterialUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_repository.change_materiallibrary'
    raise_exception = True
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_repository/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST, instance=self.object)
        else:
            # 【修改】编辑时，如果已有数据少于6行，补足到6行
            MaterialDataFormSet.extra = 1
            context['data_formset'] = MaterialDataFormSet(instance=self.object)
        context['page_title'] = f'编辑: {self.object.grade_name}'
        context['is_edit'] = True
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        data_formset = context['data_formset']
        with transaction.atomic():
            self.object = form.save()
            if data_formset.is_valid():
                data_formset.save()
            else:
                return self.render_to_response(self.get_context_data(form=form))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('repo_material_detail', kwargs={'pk': self.object.pk})


# --- 详情视图 ---
class MaterialDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_repository.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_repository/material/material_detail.html'
    context_object_name = 'material'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 1. 性能指标排序
        sorted_properties = self.object.properties.select_related(
            'test_config',
            'test_config__category'
        ).order_by(
            'test_config__category__order',
            'test_config__order'
        )
        context['sorted_properties'] = sorted_properties

        # 2. 关联项目
        related_repos = self.object.projectrepository_set.select_related(
            'project', 'project__manager'
        ).prefetch_related('project__nodes').order_by('-updated_at')
        context['related_projects'] = [repo.project for repo in related_repos]

        # 3. 【性能优化】关联配方 (使用 annotate 替代 Python 循环)
        current_std = self.request.GET.get('std', 'ISO')
        context['current_std'] = current_std
        
        # 确定标准关键词
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
        
        # 辅助函数：生成子查询
        def get_val_subquery(keyword):
            # 动态构建标准查询条件
            std_query = Q()
            for k in std_keywords:
                std_query |= Q(test_config__standard__icontains=k)
                
            return Subquery(
                FormulaTestResult.objects.filter(
                    std_query,
                    formula=OuterRef('pk'),
                    test_config__name__icontains=keyword
                ).values('value')[:1],
                output_field=DecimalField() # 注意：这里用 DecimalField
            )

        # 查询关联配方，并直接 annotate 出关键指标
        # 注意：不再 prefetch_related('test_results')，节省大量内存和IO
        formulas = self.object.formulas.select_related('creator', 'process').annotate(
            val_density=get_val_subquery('密度'),
            val_melt=get_val_subquery('熔融'),
            val_tensile=get_val_subquery('拉伸强度'),
            val_flex_strength=get_val_subquery('弯曲强度'),
            val_flex_modulus=get_val_subquery('弯曲模量'),
            val_impact=get_val_subquery('冲击'),
            val_hdt=get_val_subquery('热变形'),
        ).order_by('-created_at')
        
        # 为了兼容模板逻辑，我们需要把 annotate 的字段映射到 display_props 属性上
        # 或者直接修改模板使用 val_xxx 字段
        # 这里为了最小化修改，我们在 Python 中做一个简单的映射，但这比之前的循环快得多
        # 因为数据已经在 SQL 结果里了，不需要再查库
        
        processed_formulas = []
        for f in formulas:
            f.display_props = {
                'density': f.val_density,
                'melt': f.val_melt,
                'tensile': f.val_tensile,
                'flex_strength': f.val_flex_strength,
                'flex_modulus': f.val_flex_modulus,
                'impact': f.val_impact,
                'hdt': f.val_hdt,
            }
            processed_formulas.append(f)
            
        context['related_formulas'] = processed_formulas
        
        # 【新增】传递购物车中的配方 ID，用于前端回显勾选状态
        # 使用新的 Session Key: cart_formulas_v2
        context['cart_formula_ids'] = self.request.session.get('cart_formulas_v2', [])

        return context


# ==========================================
# 9. 材料附件管理 (新增)
# ==========================================
class MaterialFileUploadView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_repository.add_materialfile'
    model = MaterialFile
    form_class = MaterialFileForm
    template_name = 'apps/app_repository/material/material_file_form.html'  # 专用模板

    def form_valid(self, form):
        # 关联到指定的材料
        material_id = self.kwargs.get('material_id')
        material = get_object_or_404(MaterialLibrary, pk=material_id)
        form.instance.material = material
        messages.success(self.request, "附件上传成功")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        material_id = self.kwargs.get('material_id')
        context['material'] = get_object_or_404(MaterialLibrary, pk=material_id)
        context['page_title'] = '上传材料附件'
        return context

    def get_success_url(self):
        # 返回材料详情页
        return reverse('repo_material_detail', kwargs={'pk': self.object.material.id})


class MaterialFileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_repository.delete_materialfile'

    def post(self, request, pk):
        file_obj = get_object_or_404(MaterialFile, pk=pk)
        material_id = file_obj.material.id
        file_obj.delete()
        messages.success(request, "附件已删除")
        return redirect('repo_material_detail', pk=material_id)
