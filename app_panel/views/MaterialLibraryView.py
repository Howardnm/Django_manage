from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from app_panel.mixins import CustomPermissionRequiredMixin

class MaterialLibraryView(LoginRequiredMixin, CustomPermissionRequiredMixin, View):
    # 修正权限码
    permission_required = 'app_material.view_materiallibrary'

    def get(self, request):
        return render(request, 'apps/app_panel/material_library.html')
