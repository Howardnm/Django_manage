from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from app_trial_production.mixins import InjectionTaskAccessMixin
from app_trial_production.models import (
    InjectionMoldingOrder, MoldRequirement, SpecimenInventory, ProductionOrder, MoldType,
    TestingOrder,
)
from app_trial_production.forms import (
    InjectionMoldingOrderForm,
    InjectionMoldingCompleteForm, SpecimenInventoryFormSet,
)


class InjectionMoldingOrderListView(InjectionTaskAccessMixin, ListView):
    model = InjectionMoldingOrder
    template_name = 'apps/app_trial_production/injection/list.html'
    context_object_name = 'injection_orders'
    paginate_by = 20

    def get_queryset(self):
        return InjectionMoldingOrder.objects.select_related(
            'production_order', 'assigned_operator',
        ).prefetch_related('mold_requirements__mold').order_by('-created_at')


class InjectionMoldingOrderCreateView(InjectionTaskAccessMixin, CreateView):
    model = InjectionMoldingOrder
    form_class = InjectionMoldingOrderForm
    template_name = 'apps/app_trial_production/injection/form.html'

    def dispatch(self, request, *args, **kwargs):
        self.production_order = get_object_or_404(ProductionOrder, pk=kwargs.get('order_pk'))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['mold_types'] = MoldType.objects.filter(status='AVAILABLE').order_by('mold_code')
        context['production_order'] = self.production_order
        from app_formula.models import LabFormula
        context['formulas'] = LabFormula.objects.filter(
            code=self.production_order.trial_code,
            project=self.production_order.project,
        ).order_by('version')
        return context

    def form_valid(self, form):
        form.instance.production_order = self.production_order
        self.object = form.save()

        mold_count = int(self.request.POST.get('mold_count', 0))
        if mold_count > 0:
            from app_formula.models import LabFormula
            formulas = list(LabFormula.objects.filter(
                code=self.production_order.trial_code,
                project=self.production_order.project,
            ).order_by('version'))

            for i in range(mold_count):
                mold_id = self.request.POST.get(f'mold_{i}')
                if not mold_id:
                    continue
                try:
                    mold = MoldType.objects.get(pk=int(mold_id))
                except (MoldType.DoesNotExist, ValueError):
                    continue

                for formula in formulas:
                    qty_val = self.request.POST.get(f'qty_{i}_{formula.pk}', '0')
                    try:
                        qty = int(qty_val)
                    except (ValueError, TypeError):
                        qty = 0
                    if qty > 0:
                        MoldRequirement.objects.create(
                            injection_order=self.object,
                            mold=mold,
                            formula=formula,
                            specimen_quantity=qty,
                        )

        messages.success(self.request, '注塑工单已创建')
        return redirect('trial_injection_detail', pk=self.object.pk)


class InjectionMoldingOrderDetailView(InjectionTaskAccessMixin, DetailView):
    model = InjectionMoldingOrder
    template_name = 'apps/app_trial_production/injection/detail.html'
    context_object_name = 'injection_order'

    def get_queryset(self):
        return InjectionMoldingOrder.objects.select_related(
            'production_order', 'sample_split', 'sample_inventory',
            'assigned_operator',
        ).prefetch_related(
            'mold_requirements__mold', 'mold_requirements__formula',
            'specimens__mold',
        )


class InjectionMoldingCompleteView(InjectionTaskAccessMixin, UpdateView):
    model = InjectionMoldingOrder
    form_class = InjectionMoldingCompleteForm
    template_name = 'apps/app_trial_production/injection/complete.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['specimens_formset'] = SpecimenInventoryFormSet(
                self.request.POST, instance=self.object)
        else:
            context['specimens_formset'] = SpecimenInventoryFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        specimens_formset = context['specimens_formset']
        if specimens_formset.is_valid():
            self.object = form.save()
            specimens_formset.instance = self.object
            specimens_formset.save()

            # 自动关联样条到 PENDING TestingOrder
            production_order = self.object.production_order
            if production_order:
                testing_order = TestingOrder.objects.filter(
                    production_order=production_order, status='PENDING',
                ).first()
                if testing_order:
                    for specimen in self.object.specimens.all():
                        testing_order.specimens.add(specimen)

            messages.success(self.request, '注塑工单已完成')
            return redirect('trial_injection_detail', pk=self.object.pk)
        return self.render_to_response(self.get_context_data(form=form))

    def get_success_url(self):
        return reverse('trial_injection_detail', kwargs={'pk': self.object.pk})
