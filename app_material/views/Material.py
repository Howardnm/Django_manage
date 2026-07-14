from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Subquery, OuterRef, DecimalField
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.http import JsonResponse
import json

from app_material.forms import MaterialForm, MaterialDataFormSet
from app_material.models.material import MaterialLibrary, MaterialDataPoint
from app_material.utils.filters import MaterialFilter
from app_formula.models import FormulaTestResult, LabFormula
from app_material_api.integration.webhooks import send_material_webhook
from app_material.mixins import MaterialAccessMixin


class MaterialListView(MaterialAccessMixin, ListView):
    """材料列表：全员内部可见，不设部门隔离。"""
    permission_required = 'app_material.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_material/material/material_list.html'
    context_object_name = 'materials'
    paginate_by = 10

    def get_queryset(self):
        # 基类 super().get_queryset() 已处理 identity_required 和 enforce_dept_isolation=False
        qs = super().get_queryset().select_related('category').prefetch_related(
            'scenarios', 'properties', 'properties__test_config'
        )

        sort_param = self.request.GET.get('sort', '')
        metric_map = {
            'density': ('密度', 'val_density'), 'ash': ('灰分', 'val_ash'),
            'melt_index': ('熔融指数', 'val_melt'), 'tensile': ('拉伸强度', 'val_tensile'),
            'flex_strength': ('弯曲强度', 'val_flex_strength'), 'flex_modulus': ('弯曲模量', 'val_flex_modulus'),
            'impact': ('冲击', 'val_impact'), 'hdt': ('变形温度', 'val_hdt'),
        }

        if sort_param:
            clean_sort = sort_param.lstrip('-')
            if clean_sort in metric_map:
                keyword, field_name = metric_map[clean_sort]
                current_std = self.request.GET.get('std', 'ISO')
                std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
                std_query = Q()
                for k in std_keywords: std_query |= Q(test_config__standard__icontains=k)

                qs = qs.annotate(**{
                    field_name: Subquery(
                        MaterialDataPoint.objects.filter(
                            std_query, material=OuterRef('pk'),
                            test_config__name__icontains=keyword
                        ).order_by('-id').values('value')[:1],
                        output_field=DecimalField()
                    )
                })

        self.filterset = MaterialFilter(self.request.GET, queryset=qs, request=self.request)
        return self.filterset.qs.order_by('-created_at') if not sort_param else self.filterset.qs

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

        context.update({
            'cart_material_ids': self.request.session.get('cart_materials_v2', []),
            'filter': self.filterset,
            'current_sort': self.request.GET.get('sort', ''),
            'current_std': current_std
        })
        return context


class MaterialCreateView(MaterialAccessMixin, CreateView):
    """录入材料：需具备 add_materiallibrary 权限。"""
    permission_required = 'app_material.add_materiallibrary'
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
        context.update({'page_title': '录入新材料', 'is_edit': False})
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


class MaterialUpdateView(MaterialAccessMixin, UpdateView):
    """编辑材料：需具备 change_materiallibrary 权限。"""
    permission_required = 'app_material.change_materiallibrary'
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
        context.update({'page_title': f'编辑: {self.object.grade_name}', 'is_edit': True})
        return context

    def _build_error_message(self, form, formset=None):
        """构建详细的字段错误信息"""
        from django.utils.safestring import mark_safe
        lines = ['<strong>保存失败，请修正以下问题：</strong>']

        for field_name, errs in form.errors.items():
            label = form[field_name].label if field_name != '__all__' and field_name in form.fields else field_name
            for e in errs:
                lines.append(f'• {label}: {e}')

        if formset:
            for i, sf in enumerate(formset):
                if not sf.errors:
                    continue
                for field_name, errs in sf.errors.items():
                    if field_name == '__all__':
                        for e in errs:
                            lines.append(f'• 第{i+1}行: {e}')
                    else:
                        label = sf[field_name].label if field_name in sf.fields else field_name
                        for e in errs:
                            lines.append(f'• 第{i+1}行 {label}: {e}')

        return mark_safe('<br>'.join(lines))

    def form_invalid(self, form):
        messages.error(self.request, self._build_error_message(form))
        return super().form_invalid(form)

    def form_valid(self, form):
        context = self.get_context_data()
        data_formset = context['data_formset']
        with transaction.atomic():
            self.object = form.save()
            if data_formset.is_valid():
                data_formset.save()
            else:
                messages.error(self.request, self._build_error_message(form, data_formset))
                return self.render_to_response(self.get_context_data(form=form))
        messages.success(self.request, f'材料 "{self.object.grade_name}" 保存成功。')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('material_detail', kwargs={'pk': self.object.pk})


class MaterialDetailView(MaterialAccessMixin, DetailView):
    """详情展示：全员内部可见。"""
    permission_required = 'app_material.view_materiallibrary'
    model = MaterialLibrary
    template_name = 'apps/app_material/material/material_detail.html'
    context_object_name = 'material'

    def get_queryset(self):
        return super().get_queryset().select_related(
            'category'
        ).prefetch_related(
            'characteristics', 'scenarios'
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sorted_properties = self.object.properties.select_related('test_config', 'test_config__category').order_by(
            'test_config__category__order', 'test_config__order'
        )
        context['sorted_properties'] = sorted_properties

        related_projects = self.object.projects.select_related('manager').prefetch_related('nodes').order_by('-created_at')
        context['related_projects'] = related_projects

        current_std = self.request.GET.get('std', 'ISO')
        std_keywords = ['ASTM'] if current_std == 'ASTM' else ['ISO', 'GB', 'DIN', 'IEC']
        
        def get_val_subquery(keyword):
            std_query = Q()
            for k in std_keywords: std_query |= Q(test_config__standard__icontains=k)
            return Subquery(
                FormulaTestResult.objects.filter(std_query, formula=OuterRef('pk'), test_config__name__icontains=keyword).values('value')[:1],
                output_field=DecimalField()
            )

        formulas = LabFormula.objects.filter(project__material=self.object).select_related('creator', 'process').annotate(
            val_density=get_val_subquery('密度'), val_melt=get_val_subquery('熔融'),
            val_tensile=get_val_subquery('拉伸强度'), val_flex_strength=get_val_subquery('弯曲强度'),
            val_flex_modulus=get_val_subquery('弯曲模量'), val_impact=get_val_subquery('冲击'),
            val_hdt=get_val_subquery('热变形'),
        ).order_by('-created_at')
        
        for f in formulas:
            f.display_props = {
                'density': f.val_density, 'melt': f.val_melt, 'tensile': f.val_tensile,
                'flex_strength': f.val_flex_strength, 'flex_modulus': f.val_flex_modulus,
                'impact': f.val_impact, 'hdt': f.val_hdt,
            }
            
        from app_raw_material.models import PriceAvgConfig

        context.update({
            'related_formulas': formulas,
            'current_std': current_std,
            'cart_formula_ids': self.request.session.get('cart_formulas_v2', []),
            'avg_months': PriceAvgConfig.get().months,
        })
        return context


class MaterialBulkPublishView(MaterialAccessMixin, View):
    """批量发布：需具备编辑权限。"""
    permission_required = 'app_material.change_materiallibrary'
    model = MaterialLibrary

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids, action = data.get('ids', []), data.get('action')
            if not ids or action not in ['publish', 'unpublish']:
                return JsonResponse({'status': 'error', 'message': '参数错误'}, status=400)

            is_published = (action == 'publish')
            qs = self.get_queryset()
            with transaction.atomic():
                updated_count = qs.filter(pk__in=ids).update(is_published=is_published)
                for obj in qs.filter(pk__in=ids):
                    send_material_webhook('material_updated', obj)

            return JsonResponse({'status': 'success', 'message': f'成功{"发布" if is_published else "下架"} {updated_count} 个牌号'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
