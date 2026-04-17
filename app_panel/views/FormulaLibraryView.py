from django.shortcuts import render
from django.views import View
from app_formula.mixins import FormulaAccessMixin

class FormulaLibraryView(FormulaAccessMixin, View):
    """
    配方库看板：
    - 准入：需有 app_formula.view_labformula 权限。
    - 隔离：研发核心成员。
    """
    permission_required = 'app_formula.view_labformula'

    def get(self, request):
        return render(request, 'apps/app_panel/formula_library.html')
