from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from datetime import timedelta # Only timedelta is needed from datetime
from django.utils import timezone # Import timezone from Django's utilities

# 导入相关模型
from app_project.models import Project
from app_repository.models import MaterialLibrary
from app_formula.models import LabFormula
from app_process.models import ProcessProfile
from app_raw_material.models import RawMaterial


class HomeView(LoginRequiredMixin, View):
    def get(self, request):
        context = {}
        today = timezone.now() # Use timezone.now() for an aware datetime
        thirty_days_ago = today - timedelta(days=30)

        # Helper function to calculate new count and determine trend
        def get_new_count_and_trend(model):
            current_count = model.objects.count()
            
            # Count items created within the last 30 days
            # The __gte filter will now correctly compare aware datetimes
            new_count = model.objects.filter(created_at__gte=thirty_days_ago).count()

            return current_count, new_count

        # --- 总项目数 ---
        total_projects_current, project_new_count = get_new_count_and_trend(Project)
        context['total_projects'] = total_projects_current
        context['project_new_count'] = project_new_count

        # --- 总材料数 ---
        total_materials_current, material_new_count = get_new_count_and_trend(MaterialLibrary)
        context['total_materials'] = total_materials_current
        context['material_new_count'] = material_new_count

        # --- 总配方数 ---
        total_formulas_current, formula_new_count = get_new_count_and_trend(LabFormula)
        context['total_formulas'] = total_formulas_current
        context['formula_new_count'] = formula_new_count

        # --- 总工艺数 ---
        total_processes_current, process_new_count = get_new_count_and_trend(ProcessProfile)
        context['total_processes'] = total_processes_current
        context['process_new_count'] = process_new_count

        # --- 总原材料数 ---
        total_raw_materials_current, raw_material_new_count = get_new_count_and_trend(RawMaterial)
        context['total_raw_materials'] = total_raw_materials_current
        context['raw_material_new_count'] = raw_material_new_count

        return render(request, 'apps/app_panel/home.html', context)
