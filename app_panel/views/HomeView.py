from django.shortcuts import render
from django.views import View
from datetime import timedelta
from django.utils import timezone

# 导入相关模型
from app_project.models import Project
from app_material.models import MaterialLibrary
from app_formula.models import LabFormula
from app_process.models import ProcessProfile
from app_raw_material.models import RawMaterial
from app_panel.mixins import PanelAccessMixin


class HomeView(PanelAccessMixin, View):
    """
    系统首页：展示全系统数据概况。
    - 准入：内部全员 (INTERNAL_STAFF)。
    """
    def get(self, request):
        context = {}
        today = timezone.now()
        thirty_days_ago = today - timedelta(days=30)

        # Helper function to calculate new count
        def get_new_count_and_trend(model):
            current_count = model.objects.count()
            new_count = model.objects.filter(created_at__gte=thirty_days_ago).count()
            return current_count, new_count

        # --- 数据聚合 ---
        context['total_projects'], context['project_new_count'] = get_new_count_and_trend(Project)
        context['total_materials'], context['material_new_count'] = get_new_count_and_trend(MaterialLibrary)
        context['total_formulas'], context['formula_new_count'] = get_new_count_and_trend(LabFormula)
        context['total_processes'], context['process_new_count'] = get_new_count_and_trend(ProcessProfile)
        context['total_raw_materials'], context['raw_material_new_count'] = get_new_count_and_trend(RawMaterial)

        return render(request, 'apps/app_panel/home.html', context)
