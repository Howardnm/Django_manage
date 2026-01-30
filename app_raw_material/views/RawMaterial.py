from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect
from django.db.models import Q, Subquery, OuterRef, DecimalField

from app_raw_material.models import RawMaterial, RawMaterialProperty
from app_raw_material.forms import RawMaterialForm, RawMaterialPropertyFormSet
from app_raw_material.utils.filters import RawMaterialFilter

# 列表视图
class RawMaterialListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_raw_material.view_rawmaterial'
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/list.html'
    context_object_name = 'materials'
    paginate_by = 20

    def get_queryset(self):
        # 1. 基础查询
        qs = super().get_queryset().select_related('category', 'supplier').prefetch_related('suitable_materials', 'properties__test_config').order_by('-created_at')
        
        # 2. 获取排序参数
        sort_param = self.request.GET.get('sort', '')
        
        # 3. 映射表 (与 MaterialListView 保持一致)
        metric_map = {
            'density': ('密度', 'val_density'),
            'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融指数', 'val_melt'),
            'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'),
            'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'),
            'hdt': ('变形温度', 'val_hdt'),
        }

        # 4. 动态 Annotate (用于排序)
        if sort_param:
            clean_sort = sort_param.lstrip('-')
            if clean_sort in metric_map:
                keyword, field_name = metric_map[clean_sort]
                
                # 获取当前标准
                current_std = self.request.GET.get('std', 'ISO')
                std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
                
                std_query = Q()
                for k in std_keywords:
                    std_query |= Q(test_config__standard__icontains=k)
                
                qs = qs.annotate(**{
                    field_name: Subquery(
                        RawMaterialProperty.objects.filter(
                            std_query,
                            raw_material=OuterRef('pk'),
                            test_config__name__icontains=keyword
                        ).order_by('-id').values('value')[:1],
                        output_field=DecimalField()
                    )
                })

        # 【修复】传入 request 参数，以便 FilterSet 内部可以访问 self.request (用于性能筛选)
        self.filterset = RawMaterialFilter(self.request.GET, queryset=qs, request=self.request)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Python 内存填充数据 (与 MaterialListView 逻辑一致)
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

            if not hasattr(mat, 'val_density'): mat.val_density = find_val_in_memory("密度")
            if not hasattr(mat, 'val_ash'): mat.val_ash = find_val_in_memory("灰分")
            if not hasattr(mat, 'val_melt'): mat.val_melt = find_val_in_memory("熔融指数")
            if not hasattr(mat, 'val_tensile'): mat.val_tensile = find_val_in_memory("拉伸强度")
            if not hasattr(mat, 'val_flex_strength'): mat.val_flex_strength = find_val_in_memory("弯曲强度")
            if not hasattr(mat, 'val_flex_modulus'): mat.val_flex_modulus = find_val_in_memory("弯曲模量")
            if not hasattr(mat, 'val_impact'): mat.val_impact = find_val_in_memory("冲击")
            if not hasattr(mat, 'val_hdt'): mat.val_hdt = find_val_in_memory("变形温度")

        # 【新增】传递购物车中的原材料 ID，用于前端回显勾选状态
        # 使用新的 Session Key: cart_raw_materials_v2
        context['cart_raw_material_ids'] = self.request.session.get('cart_raw_materials_v2', [])

        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        context['current_std'] = current_std
        return context

# 详情视图
class RawMaterialDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_raw_material.view_rawmaterial'
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/detail.html'
    context_object_name = 'material'

    def get_queryset(self):
        return super().get_queryset().select_related('category', 'supplier').prefetch_related('properties__test_config')

# 创建视图 (带 FormSet)
class RawMaterialCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_raw_material.add_rawmaterial'
    raise_exception = True
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增原材料'
        if self.request.POST:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST)
        else:
            # 【修改】预留 4 行空表单
            RawMaterialPropertyFormSet.extra = 4
            context['property_formset'] = RawMaterialPropertyFormSet(queryset=RawMaterialProperty.objects.none())
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        property_formset = context['property_formset']
        
        with transaction.atomic():
            self.object = form.save()
            if property_formset.is_valid():
                property_formset.instance = self.object
                property_formset.save()
            else:
                return self.render_to_response(self.get_context_data(form=form))
                
        messages.success(self.request, "原材料已添加")
        # 【修改】跳转到详情页
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('raw_material_detail', kwargs={'pk': self.object.pk})

# 【新增】原材料复制视图
class RawMaterialDuplicateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_raw_material.add_rawmaterial'
    raise_exception = True
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_object(self, queryset=None):
        original_material = super().get_object(queryset)
        return original_material

    # 重新实现为 CreateView 逻辑
    def dispatch(self, request, *args, **kwargs):
        self.original_material = self.get_object()
        return super().dispatch(request, *args, **kwargs)
        
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '复制原材料'
        
        # 如果是 GET 请求，预填充 FormSet 数据
        if not self.request.POST:
            # 复制性能指标
            prop_initial = []
            for prop in self.original_material.properties.all():
                prop_initial.append({
                    'test_config': prop.test_config,
                    'value': prop.value,
                    'value_text': prop.value_text,
                    'test_date': prop.test_date,
                    'remark': prop.remark,
                })
            context['property_formset'] = RawMaterialPropertyFormSet(initial=prop_initial)
            context['property_formset'].extra = len(prop_initial)
        else:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST)
            
        return context

    def get_initial(self):
        initial = super().get_initial()
        # 预填充主表单数据
        initial.update({
            'name': f"{self.original_material.name} (副本)",
            'model_name': self.original_material.model_name,
            'warehouse_code': None, # 清空编码
            'category': self.original_material.category,
            'supplier': self.original_material.supplier,
            'usage_method': self.original_material.usage_method,
            'cost_price': self.original_material.cost_price,
            'purchase_date': self.original_material.purchase_date,
            'suitable_materials': self.original_material.suitable_materials.all(),
        })
        return initial

    def form_valid(self, form):
        context = self.get_context_data()
        property_formset = context['property_formset']
        
        with transaction.atomic():
            # 创建新原材料
            form.instance.pk = None # 确保是新建
            self.object = form.save()
            
            if property_formset.is_valid():
                property_formset.instance = self.object
                property_formset.save()
            else:
                return self.render_to_response(self.get_context_data(form=form))
                
        messages.success(self.request, "原材料已复制并创建")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('raw_material_detail', kwargs={'pk': self.object.pk})

# 更新视图 (带 FormSet)
class RawMaterialUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_raw_material.change_rawmaterial'
    raise_exception = True
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑原材料'
        if self.request.POST:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST, instance=self.object)
        else:
            # 【修改】编辑时，如果已有数据少于4行，补足到4行 (这里简单设为1，方便添加)
            RawMaterialPropertyFormSet.extra = 1
            context['property_formset'] = RawMaterialPropertyFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        property_formset = context['property_formset']
        
        with transaction.atomic():
            self.object = form.save()
            if property_formset.is_valid():
                property_formset.save()
            else:
                return self.render_to_response(self.get_context_data(form=form))
                
        messages.success(self.request, "原材料已更新")
        # 【修改】跳转到详情页
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('raw_material_detail', kwargs={'pk': self.object.pk})
