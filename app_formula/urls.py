from django.urls import path
from .views.LabFormula import *
from .views.FormulaCompare import FormulaCompareView, FormulaCompareCartView

urlpatterns = [
    path('list/', LabFormulaListView.as_view(), name='formula_list'),
    path('add/', LabFormulaCreateView.as_view(), name='formula_add'),
    path('<int:pk>/', LabFormulaDetailView.as_view(), name='formula_detail'),
    path('<int:pk>/edit/', LabFormulaUpdateView.as_view(), name='formula_edit'),
    path('<int:pk>/duplicate/', LabFormulaDuplicateView.as_view(), name='formula_duplicate'),
    path('compare/', FormulaCompareView.as_view(), name='formula_compare'),
    # 【新增】对比购物车 API
    path('api/compare-cart/', FormulaCompareCartView.as_view(), name='formula_compare_cart'),
]
