import logging

from django.shortcuts import render
from django.views import View

from app_panel.mixins import PanelAccessMixin

logger = logging.getLogger(__name__)


class SchedulingCalendarView(PanelAccessMixin, View):
    """看板工作台 — 只读排产日历页面。

    仅用于查看挤出排产日历（月/周/日/日程视图切换），
    排产单不可点击跳转、不可拖拽/调整/取消排期。
    L1/L2: PanelAccessMixin (module_code='panel') 从 DB 读取。
    L3: 展示跨模块聚合数据，卡片级只读，无写操作。
    """

    permission_required = []

    def get(self, request):
        return render(request, 'apps/app_panel/scheduling_calendar.html', {})