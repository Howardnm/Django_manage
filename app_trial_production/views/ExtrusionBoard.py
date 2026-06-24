import logging

from django.views.generic import TemplateView
from django.utils import timezone

from app_trial_production.mixins import ExtrusionTaskAccessMixin

logger = logging.getLogger(__name__)


class ExtrusionBoardView(ExtrusionTaskAccessMixin, TemplateView):
    """挤出排产工作台 — 日历 + 待排产池 + 生产中看板"""
    template_name = 'apps/app_trial_production/extrusion/board.html'
    enforce_dept_isolation = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        default_dt = now.replace(hour=8, minute=0, second=0, microsecond=0)
        context['default_schedule_time'] = default_dt.strftime('%Y-%m-%dT%H:%M')
        return context
