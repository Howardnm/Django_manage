import logging

from django.shortcuts import render
from django.views import View

from app_trial_production.mixins import DashboardAccessMixin

logger = logging.getLogger(__name__)


class SchedulingCalendarView(DashboardAccessMixin, View):
    """试验排产中心 — 只读排产日历页面。

    用于查看挤出排产日历（月/周/日/日程视图切换），
    排产单可点击跳转详情页，但不可拖拽/调整/取消排期。
    L1/L2: DashboardAccessMixin (module_code='trial_production.dashboard') 从 DB 读取。
    L3: 展示跨模块聚合数据，卡片级只读，无写操作。
    """

    permission_required = []
    enforce_dept_isolation = False

    def get(self, request):
        return render(request, 'apps/app_trial_production/extrusion/scheduling_calendar.html', {})
