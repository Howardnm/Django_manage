import logging

from django.views.generic import ListView, DetailView, View
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from app_trial_production.mixins import ExtrusionTaskAccessMixin
from app_trial_production.models import ExtrusionTask, ProductionOrder
from app_trial_production.filters import ExtrusionTaskFilter
from app_trial_production.forms import ExtrusionRecordForm
from app_trial_production.services import ExtrusionTaskService

logger = logging.getLogger(__name__)


class ExtrusionTaskListView(ExtrusionTaskAccessMixin, ListView):
    """挤出任务列表"""
    model = ExtrusionTask
    template_name = 'apps/app_trial_production/extrusion/list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        qs = qs.select_related(
            'production_order', 'production_order__project',
            'operator',
        ).filter(
            production_order__extrusion_scheduled_date__isnull=False,
            production_order__status__in=[
                'ACCEPTED', 'EXTRUDING', 'INJECTION_MOLDING', 'TESTING', 'COMPLETED',
            ],
        ).order_by('-created_at')

        self.filter = ExtrusionTaskFilter(self.request.GET, queryset=qs)
        qs = self.filter.qs
        if not self.request.GET.get('sort'):
            qs = qs.order_by('-created_at')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        sort_list = self.request.GET.getlist('sort')
        context['current_sort'] = sort_list[0] if sort_list else ''
        return context


class ExtrusionTaskDetailView(ExtrusionTaskAccessMixin, DetailView):
    """挤出任务详情"""
    model = ExtrusionTask
    template_name = 'apps/app_trial_production/extrusion/detail.html'
    context_object_name = 'task'
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        qs = super().get_queryset()
        if qs is None:
            qs = self.model.objects.all()
        return qs.select_related(
            'production_order', 'production_order__project',
            'production_order__process_profile',
            'production_order__process_profile__machine',
            'operator',
        ).filter(production_order_id=self.kwargs['pk'])

    def get_object(self, queryset=None):
        # ExtrusionTask 按 production_order_id 查找，不能直接用 get_object_or_deny 的 pk 查找
        qs = self.model.objects.all()
        obj = get_object_or_404(qs, production_order_id=self.kwargs['pk'])
        self.check_object_permission(obj)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['production_order'] = self.object.production_order
        context['process_profile'] = self.object.production_order.process_profile

        # 温度区域列表，避免模板中 if/elif 链
        task = self.object
        context['temperature_zones'] = [
            (f'第{i}区', getattr(task, f'temp_zone_{i}'))
            for i in range(1, 13)
        ]
        context['temperature_zones'].append(('机头', task.temp_head))

        return context


class ExtrusionTaskStartView(ExtrusionTaskAccessMixin, View):
    """开始挤出任务"""

    def post(self, request, pk):
        task = get_object_or_404(ExtrusionTask, production_order_id=pk)
        if task.status != 'PENDING':
            messages.warning(request, '任务状态不允许开始')
            return redirect('trial_extrusion_detail', pk=pk)

        # 操作员归属校验
        if task.operator_id and task.operator_id != request.user.pk:
            if not request.user.is_superuser:
                raise PermissionDenied("您不是该任务分配的挤出操作员")

        try:
            ExtrusionTaskService.start_task(task, request.user)
            messages.success(request, '挤出任务已开始')
        except Exception:
            logger.exception(f"Extrusion start failed: pk={pk}")
            messages.error(request, '系统错误，请稍后重试')
        return redirect('trial_extrusion_record', pk=pk)


class ExtrusionRecordFormView(ExtrusionTaskAccessMixin, View):
    """挤出参数记录表单"""
    template_name = 'apps/app_trial_production/extrusion/record_form.html'

    def get(self, request, pk):
        task = get_object_or_404(
            ExtrusionTask.objects.select_related(
                'production_order', 'production_order__process_profile',
                'production_order__process_profile__machine',
            ),
            production_order_id=pk,
        )

        # 从工艺方案预填（始终执行，form.initial 仅对实例中仍为默认值的字段生效）
        form = ExtrusionRecordForm(instance=task)
        process_profile = task.production_order.process_profile
        if process_profile:
            for field in ExtrusionTask.ALL_PARAM_FIELDS:
                pp_val = getattr(process_profile, field, None)
                if pp_val:
                    form.initial[field] = pp_val

        return render(request, self.template_name, {
            'task': task,
            'form': form,
            'production_order': task.production_order,
            'process_profile': process_profile,
        })

    def post(self, request, pk):
        task = get_object_or_404(ExtrusionTask, production_order_id=pk)
        form = ExtrusionRecordForm(request.POST, instance=task)
        if form.is_valid():
            try:
                ExtrusionTaskService.save_record(task, form.cleaned_data, request.user)
                messages.success(request, '挤出生产记录已保存')
            except Exception:
                logger.exception(f"Extrusion record save failed: pk={pk}")
                messages.error(request, '系统错误，请稍后重试')
            return redirect('trial_extrusion_detail', pk=pk)

        return render(request, self.template_name, {
            'task': task,
            'form': form,
            'production_order': task.production_order,
        })


class ExtrusionTaskCompleteView(ExtrusionTaskAccessMixin, View):
    """完成挤出任务"""

    def post(self, request, pk):
        task = get_object_or_404(ExtrusionTask, production_order_id=pk)
        if task.status != 'IN_PROGRESS':
            messages.warning(request, '当前任务状态不允许完成')
            return redirect('trial_extrusion_detail', pk=pk)

        if not request.user.is_superuser and task.operator_id:
            if task.operator_id != request.user.pk:
                raise PermissionDenied("您不是该任务分配的挤出操作员")

        try:
            ExtrusionTaskService.complete_task(task, request.user)
            messages.success(request, '挤出任务已完成')
        except Exception:
            logger.exception(f"Extrusion complete failed: pk={pk}")
            messages.error(request, '系统错误，请稍后重试')
        return redirect('trial_order_detail', pk=pk)
