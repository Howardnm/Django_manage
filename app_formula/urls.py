from django.urls import path
from .views.LabFormula import *
from .views.FormulaCompare import FormulaCompareView, FormulaCompareCartView
from .views.FormulaChartCompare import FormulaChartCompareView, FormulaChartDataAPI
from .views.FormulaSearchAPI import FormulaAutocompleteView

urlpatterns = [
    path('list/', LabFormulaListView.as_view(), name='formula_list'),
    path('prepare/', prepare_formula, name='formula_prepare'),
    path('import/prepare/', formula_import_prepare, name='formula_import_prepare'),
    path('add/', LabFormulaCreateView.as_view(), name='formula_add'),
    path('<int:pk>/', LabFormulaDetailView.as_view(), name='formula_detail'),
    path('<int:pk>/edit/', LabFormulaUpdateView.as_view(), name='formula_edit'),
    path('<int:pk>/duplicate/', LabFormulaDuplicateView.as_view(), name='formula_duplicate'),
    path('<int:pk>/edit/import/', formula_import_from, name='formula_import'),
    path('compare/', FormulaCompareView.as_view(), name='formula_compare'),
    path('chart-compare/', FormulaChartCompareView.as_view(), name='formula_chart_compare'),
    # APIs
    path('api/compare-cart/', FormulaCompareCartView.as_view(), name='formula_compare_cart'),
    path('api/chart-data/', FormulaChartDataAPI.as_view(), name='formula_chart_data_api'),
    path('api/search/', FormulaAutocompleteView.as_view(), name='formula_api_search'),
]
