import logging

from django.http import JsonResponse
from django.views import View

from app_trial_production.mixins import DashboardAccessMixin
from app_trial_production.services.extrusion_service import build_extrusion_calendar_events

logger = logging.getLogger(__name__)


class SchedulingCalendarEventsView(DashboardAccessMixin, View):
    """试验排产中心 — 只读排产日历事件数据 API（GET only，无写操作）。

    L1/L2: DashboardAccessMixin (module_code='trial_production.dashboard') 从 DB 读取。
    复用挤出排产日历事件序列化函数，与排产工作台数据保持一致。
    """

    permission_required = []
    enforce_dept_isolation = False

    def get(self, request):
        events = build_extrusion_calendar_events(
            request.GET.get('start', ''),
            request.GET.get('end', ''),
        )
        return JsonResponse(events, safe=False)
