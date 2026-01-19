from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, FloatField
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_repository.forms import MaterialForm, MaterialDataFormSet, MaterialFileForm
from app_repository.models import MaterialLibrary, MaterialDataPoint, MaterialFile
from app_repository.utils.filters import MaterialFilter


# ==========================================
# 2. 材料库视图 (Material)
# ==========================================

# --- 列表视图 (含 Tab 切换逻辑) ---
class MaterialListView(LoginRequiredMixin, ListView):
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
                        output_field=FloatField()
                    )
                })

        # 4. 接入过滤器
        self.filterset = MaterialFilter(self.request.GET, queryset=qs)

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
            if not hasattr(mat, 'val_melt'): mat.val_melt = find_val_in_memory("熔融指数")
            if not hasattr(mat, 'val_tensile'): mat.val_tensile = find_val_in_memory("拉伸强度")
            if not hasattr(mat, 'val_flex_strength'): mat.val_flex_strength = find_val_in_memory("弯曲强度")
            if not hasattr(mat, 'val_flex_modulus'): mat.val_flex_modulus = find_val_in_memory("弯曲模量")
            if not hasattr(mat, 'val_impact'): mat.val_impact = find_val_in_memory("冲击")

            # HDT 特殊处理：因为列表显示的是合并列，这里只取一个主要的用于排序显示
            # 实际上列表页 Template 并没有直接用 val_hdt，而是用了 val_hdt 作为排序参考
            if not hasattr(mat, 'val_hdt'): mat.val_hdt = find_val_in_memory("变形温度")

        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        context['current_std'] = current_std
        return context


# --- 创建视图 ---
class MaterialCreateView(LoginRequiredMixin, CreateView):
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_repository/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST)
        else:
            context['data_formset'] = MaterialDataFormSet()
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
class MaterialUpdateView(LoginRequiredMixin, UpdateView):
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_repository/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST, instance=self.object)
        else:
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
class MaterialDetailView(LoginRequiredMixin, DetailView):
    model = MaterialLibrary
    template_name = 'apps/app_repository/material/material_detail.html'
    context_object_name = 'material'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 【核心修复】显式指定排序规则
        # 1. select_related: 优化查询，把关联的 Config 和 Category 一次查出来
        # 2. order_by:
        #    第一级: test_config__category__order (物理 > 机械 > 热学)
        #    第二级: test_config__order (密度 > 熔融指数 > 收缩率)
        sorted_properties = self.object.properties.select_related(
            'test_config',
            'test_config__category'
        ).order_by(
            'test_config__category__order',
            'test_config__order'  # <--- 这就是你缺失的“组内排序”
        )

        # 将排好序的 QuerySet 传给模板
        context['sorted_properties'] = sorted_properties

        # 同时把关联项目也查出来 (保持你原有的逻辑)
        related_repos = self.object.projectrepository_set.select_related(
            'project', 'project__manager'
        ).prefetch_related('project__nodes').order_by('-updated_at')
        context['related_projects'] = [repo.project for repo in related_repos]

        return context


# ==========================================
# 9. 材料附件管理 (新增)
# ==========================================
class MaterialFileUploadView(LoginRequiredMixin, CreateView):
    model = MaterialFile
    form_class = MaterialFileForm
    template_name = 'apps/app_repository/material_info/material_file_form.html'  # 专用模板

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


class MaterialFileDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        file_obj = get_object_or_404(MaterialFile, pk=pk)
        material_id = file_obj.material.id
        file_obj.delete()
        messages.success(request, "附件已删除")
        return redirect('repo_material_detail', pk=material_id)
