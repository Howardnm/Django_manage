from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

class FormulaLibraryView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'apps/app_panel/formula_library.html')
