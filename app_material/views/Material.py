from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, FloatField, DecimalField
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView

from app_material.forms import MaterialForm, MaterialDataFormSet, MaterialFileForm
from app_material.models.material import MaterialLibrary, MaterialDataPoint, MaterialFile
from app_material.utils.filters import MaterialFilter
from app_formula.models import FormulaTestResult


# ==========================================
# 2. 材料库视图 (Material)
# ==========================================

class MaterialListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'app_material.view_materiallibrary' # 修正权限码
    model = MaterialLibrary
    template_name = 'apps/app_material/material/material_list.html' # 修正模板路径
    context_object_name = 'materials'
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset() \
            .select_related('category') \
            .prefetch_related('scenarios', 'properties', 'properties__test_config')

        sort_param = self.request.GET.get('sort', '')
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

        if sort_param:
            clean_sort = sort_param.lstrip('-')
            if clean_sort in metric_map:
                keyword, field_name = metric_map[clean_sort]
                current_std = self.request.GET.get('std', 'ISO')
                std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']

                std_query = Q()
                for k in std_keywords:
                    std_query |= Q(test_config__standard__icontains=k)

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

        self.filterset = MaterialFilter(self.request.GET, queryset=qs, request=self.request)
        if not sort_param:
            return self.filterset.qs.order_by('-created_at')
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
            if not hasattr(mat, 'val_hdt'): mat.val_hdt = find_val_in_memory("热变形")
            if not hasattr(mat, 'val_hdt'): mat.val_hdt = find_val_in_memory("变形温度")

        context['cart_material_ids'] = self.request.session.get('cart_materials_v2', [])
        context['filter'] = self.filterset
        context['current_sort'] = self.request.GET.get('sort', '')
        context['current_std'] = current_std
        return context


class MaterialCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_material.add_materiallibrary'
    raise_exception = True
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_material/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST)
        else:
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
        return reverse('material_detail', kwargs={'pk': self.object.pk})


class MaterialUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = 'app_material.change_materiallibrary'
    raise_exception = True
    model = MaterialLibrary
    form_class = MaterialForm
    template_name = 'apps/app_material/material/material_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['data_formset'] = MaterialDataFormSet(self.request.POST, instance=self.object)
        else:
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
        return reverse('material_detail', kwargs={'pk': self.object.pk})


class MaterialDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = 'app_material.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_material/material/material_detail.html'
    context_object_name = 'material'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sorted_properties = self.object.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        context['sorted_properties'] = sorted_properties

        related_repos = self.object.projectrepository_set.select_related('project', 'project__manager').prefetch_related('project__nodes').order_by('-updated_at')
        context['related_projects'] = [repo.project for repo in related_repos]

        current_std = self.request.GET.get('std', 'ISO')
        context['current_std'] = current_std
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
        
        def get_val_subquery(keyword):
            std_query = Q()
            for k in std_keywords:
                std_query |= Q(test_config__standard__icontains=k)
            return Subquery(
                FormulaTestResult.objects.filter(std_query, formula=OuterRef('pk'), test_config__name__icontains=keyword).values('value')[:1],
                output_field=DecimalField()
            )

        formulas = self.object.formulas.select_related('creator', 'process').annotate(
            val_density=get_val_subquery('密度'),
            val_melt=get_val_subquery('熔融'),
            val_tensile=get_val_subquery('拉伸强度'),
            val_flex_strength=get_val_subquery('弯曲强度'),
            val_flex_modulus=get_val_subquery('弯曲模量'),
            val_impact=get_val_subquery('冲击'),
            val_hdt=get_val_subquery('热变形'),
        ).order_by('-created_at')
        
        processed_formulas = []
        for f in formulas:
            f.display_props = {
                'density': f.val_density, 'melt': f.val_melt, 'tensile': f.val_tensile,
                'flex_strength': f.val_flex_strength, 'flex_modulus': f.val_flex_modulus,
                'impact': f.val_impact, 'hdt': f.val_hdt,
            }
            processed_formulas.append(f)
            
        context['related_formulas'] = processed_formulas
        context['cart_formula_ids'] = self.request.session.get('cart_formulas_v2', [])
        return context


class MaterialFileUploadView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = 'app_material.add_materialfile'
    model = MaterialFile
    form_class = MaterialFileForm
    template_name = 'apps/app_material/material/material_file_form.html'

    def form_valid(self, form):
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
        return reverse('material_detail', kwargs={'pk': self.object.material.id})


class MaterialFileDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_material.delete_materialfile'

    def post(self, request, pk):
        file_obj = get_object_or_404(MaterialFile, pk=pk)
        material_id = file_obj.material.id
        file_obj.delete()
        messages.success(request, "附件已删除")
        return redirect('material_detail', pk=material_id)
