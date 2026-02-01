from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

class RawMaterialLibraryView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'apps/app_panel/raw_material_library.html')
