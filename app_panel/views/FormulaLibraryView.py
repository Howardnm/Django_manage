from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from app_panel.mixins import CustomPermissionRequiredMixin # 导入自定义的 Mixin

class FormulaLibraryView(LoginRequiredMixin, CustomPermissionRequiredMixin, View): # 替换 Mixin
    permission_required = 'app_formula.view_labformula'
    # 移除 raise_exception = True
    # raise_exception = True

    def get(self, request):
        return render(request, 'apps/app_panel/formula_library.html')
