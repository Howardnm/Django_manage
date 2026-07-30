import logging

from django.shortcuts import render
from django.views import View
from datetime import timedelta
from django.utils import timezone

from app_panel.mixins import PanelAccessMixin
from app_project.models import Project
from app_material.models import MaterialLibrary
from app_formula.models import LabFormula
from app_process.models import ProcessProfile
from app_raw_material.models import RawMaterial

logger = logging.getLogger(__name__)


class SystemOverviewView(PanelAccessMixin, View):
    """系统总览：全系统资源统计数据。

    L1/L2: PanelAccessMixin (module_code='panel') 从 DB 读取。
    L3: app_project.view_project（参照 CustomerActivityOverviewView 模式）。
    """

    permission_required = 'app_project.view_project'

    def get(self, request):
        context = {}
        today = timezone.now()
        thirty_days_ago = today - timedelta(days=30)

        def get_new_count_and_trend(model):
            current_count = model.objects.count()
            new_count = model.objects.filter(created_at__gte=thirty_days_ago).count()
            return current_count, new_count

        # ── 数据聚合 ──
        context['total_projects'], context['project_new_count'] = get_new_count_and_trend(Project)
        context['total_materials'], context['material_new_count'] = get_new_count_and_trend(MaterialLibrary)
        context['total_formulas'], context['formula_new_count'] = get_new_count_and_trend(LabFormula)
        context['total_processes'], context['process_new_count'] = get_new_count_and_trend(ProcessProfile)
        context['total_raw_materials'], context['raw_material_new_count'] = get_new_count_and_trend(RawMaterial)

        return render(request, 'apps/app_panel/system_overview.html', context)
