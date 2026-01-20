from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.db import transaction
from django.shortcuts import redirect

from app_raw_material.models import RawMaterial
from app_raw_material.forms import RawMaterialForm, RawMaterialPropertyFormSet
from app_raw_material.utils.filters import RawMaterialFilter

# 列表视图
class RawMaterialListView(LoginRequiredMixin, ListView):
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/list.html'
    context_object_name = 'materials'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related('category', 'supplier').order_by('-created_at')
        self.filterset = RawMaterialFilter(self.request.GET, queryset=qs)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filterset
        return context

# 详情视图
class RawMaterialDetailView(LoginRequiredMixin, DetailView):
    model = RawMaterial
    template_name = 'apps/app_raw_material/material/detail.html'
    context_object_name = 'material'

    def get_queryset(self):
        return super().get_queryset().select_related('category', 'supplier').prefetch_related('properties__test_config')

# 创建视图 (带 FormSet)
class RawMaterialCreateView(LoginRequiredMixin, CreateView):
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '新增原材料'
        if self.request.POST:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST)
        else:
            context['property_formset'] = RawMaterialPropertyFormSet()
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

# 更新视图 (带 FormSet)
class RawMaterialUpdateView(LoginRequiredMixin, UpdateView):
    model = RawMaterial
    form_class = RawMaterialForm
    template_name = 'apps/app_raw_material/material/form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑原材料'
        if self.request.POST:
            context['property_formset'] = RawMaterialPropertyFormSet(self.request.POST, instance=self.object)
        else:
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
