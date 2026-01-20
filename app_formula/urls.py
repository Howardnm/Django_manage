from django.urls import path
from .views.LabFormula import *

urlpatterns = [
    path('list/', LabFormulaListView.as_view(), name='formula_list'),
    path('add/', LabFormulaCreateView.as_view(), name='formula_add'),
    path('<int:pk>/', LabFormulaDetailView.as_view(), name='formula_detail'),
    path('<int:pk>/edit/', LabFormulaUpdateView.as_view(), name='formula_edit'),
]
