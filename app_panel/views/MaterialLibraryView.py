from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

class MaterialLibraryView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_repository.view_materiallibrary' # 修改为 app_repository 的权限
    raise_exception = True

    def get(self, request):
        return render(request, 'apps/app_panel/material_library.html')
