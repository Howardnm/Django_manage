from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin

class FormulaLibraryView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'app_formula.view_labformula' # 修改为 app_formula 的权限
    raise_exception = True

    def get(self, request):
        return render(request, 'apps/app_panel/formula_library.html')
