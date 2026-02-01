from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

class MaterialLibraryView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'apps/app_panel/material_library.html')
