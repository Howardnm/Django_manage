from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

class RawMaterialLibraryView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_raw_material.view_rawmaterial' # 修改为 app_raw_material 的权限
    raise_exception = True

    def get(self, request):
        return render(request, 'apps/app_panel/raw_material_library.html')
