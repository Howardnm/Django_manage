from django.urls import path
from .views.LabFormula import *
from .views.FormulaCompare import FormulaCompareView, FormulaCompareCartView
from .views.FormulaChartCompare import FormulaChartCompareView, FormulaChartDataAPI
from .views.FormulaSearchAPI import FormulaAutocompleteView, ExperimentOrderAutocompleteView

urlpatterns = [
    path('list/', LabFormulaListView.as_view(), name='formula_list'),
    path('prepare/', FormulaPrepareView.as_view(), name='formula_prepare'),
    path('import/prepare/', FormulaImportPrepareView.as_view(), name='formula_import_prepare'),
    path('add/', LabFormulaCreateView.as_view(), name='formula_add'),
    path('add/new/', FormulaStartFreshView.as_view(), name='formula_add_fresh'),
    path('<int:pk>/', LabFormulaDetailView.as_view(), name='formula_detail'),
    path('<int:pk>/edit/', LabFormulaUpdateView.as_view(), name='formula_edit'),
    path('<int:pk>/duplicate/', LabFormulaDuplicateView.as_view(), name='formula_duplicate'),
    path('<int:pk>/edit/import/', FormulaImportFromView.as_view(), name='formula_import'),
    path('compare/', FormulaCompareView.as_view(), name='formula_compare'),
    path('chart-compare/', FormulaChartCompareView.as_view(), name='formula_chart_compare'),
    # APIs
    path('api/compare-cart/', FormulaCompareCartView.as_view(), name='formula_compare_cart'),
    path('api/chart-data/', FormulaChartDataAPI.as_view(), name='formula_chart_data_api'),
    path('api/search/', FormulaAutocompleteView.as_view(), name='formula_api_search'),
    path('api/search-experiment/', ExperimentOrderAutocompleteView.as_view(), name='formula_api_search_experiment'),
]
