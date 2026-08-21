"""注塑模块 — 样品库存管理视图。

管辖范围：
  - PELLET + FOR_INJECTION（待打样颗粒）
  - SPECIMEN + FOR_TESTING（待测试样条）
"""
import logging

from django.db.models import Q
from django.views.generic import View
from django.shortcuts import render
from app_mold_injection.mixins import InjectionTaskAccessMixin
from app_trial_production.models import SampleInventory
from app_trial_production.filters import SampleInventoryFilter
from app_trial_production.services import SampleInventoryService

logger = logging.getLogger(__name__)


class MoldSampleListView(InjectionTaskAccessMixin, View):
    """注塑模块样品库存列表 — 待打样颗粒 + 待测试样条，按工单分组表格呈现。"""

    template_name = 'apps/app_mold_injection/sample/list.html'
    paginate_by = 20
    permission_required = 'app_mold_injection.view_injectiontask'

    def _get_filtered_qs(self, request):
        qs = SampleInventory.objects.select_related(
            'production_order',
            'production_order__project',
            'formula',
            'mold',
            'injection_task',
        ).prefetch_related('injection_tasks')

        # Hard-code 范围：待打样颗粒 + 待测试样条
        qs = qs.filter(
            Q(type=SampleInventory.Type.PELLET, sub_type=SampleInventory.SubType.FOR_INJECTION) |
            Q(type=SampleInventory.Type.SPECIMEN, sub_type=SampleInventory.SubType.FOR_TESTING)
        )

        self.filter = SampleInventoryFilter(request.GET, queryset=qs)
        qs = self.filter.qs

        # 首页默认：在实验房
        status_param = request.GET.get('status', '')
        if status_param == 'ALL':
            pass
        elif not status_param:
            qs = qs.filter(status=SampleInventory.Status.IN_LAB)

        return qs.order_by('-created_at')

    def get(self, request):
        samples_qs = self._get_filtered_qs(request)
        order_groups, _ = SampleInventoryService.build_order_groups(samples_qs)

        from django.core.paginator import Paginator
        page_num = int(request.GET.get('page', 1))
        paginator = Paginator(order_groups, self.paginate_by)
        page_obj = paginator.get_page(page_num)

        context = {
            'order_groups': order_groups,
            'page_obj': page_obj,
            'paginator': paginator,
            'filter': self.filter,
            'current_status': request.GET.get('status', 'IN_LAB'),
        }
        return render(request, self.template_name, context)


