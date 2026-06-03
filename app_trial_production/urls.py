from django.urls import path
from .views.ProductionOrder import (
    ProductionOrderListView, ProductionOrderDetailView,
    ProductionOrderCreateView, ProductionOrderUpdateView,
    ProductionOrderInitiateView, ProductionOrderStartWorkflowView,
    ProductionOrderCompleteExtrusionView,
)
from .views.Dashboard import TrialDashboardView
from .views.MoldType import (
    MoldTypeListView, MoldTypeCreateView, MoldTypeUpdateView,
)
from .views.ExtrusionRecord import ExtrusionRecordCreateView
from .views.SampleSplit import SampleSplitManageView
from .views.InjectionMolding import (
    InjectionMoldingOrderCreateView, InjectionMoldingOrderDetailView,
    InjectionMoldingCompleteView, InjectionMoldingOrderListView,
)
from .views.TestingOrder import (
    TestingOrderDetailView,
    TestingOrderFillResultsView, TestingOrderWriteBackView,
    TestingOrderListView,
)
from .views.ColorPowderBOM import (
    ColorPowderBOMListView, ColorPowderBOMFillView,
)
from .views.SampleInventory import SampleInventoryListView, SampleInventoryShipView
from .views.Config import TrialConfigView
from .views.Autocomplete import TrialAutocompleteView

urlpatterns = [
    # Config
    path('config/', TrialConfigView.as_view(), name='trial_production_config'),

    # Dashboard
    path('', TrialDashboardView.as_view(), name='trial_production_dashboard'),

    # Production Orders
    path('orders/', ProductionOrderListView.as_view(), name='trial_production_order_list'),
    path('orders/create/', ProductionOrderCreateView.as_view(), name='trial_production_order_create'),
    path('orders/initiate/', ProductionOrderInitiateView.as_view(), name='trial_production_order_initiate'),
    path('orders/<int:pk>/', ProductionOrderDetailView.as_view(), name='trial_production_order_detail'),
    path('orders/<int:pk>/edit/', ProductionOrderUpdateView.as_view(), name='trial_production_order_edit'),
    path('orders/<int:pk>/start-workflow/', ProductionOrderStartWorkflowView.as_view(), name='trial_production_order_start_workflow'),
    path('orders/<int:pk>/complete-extrusion/', ProductionOrderCompleteExtrusionView.as_view(), name='trial_production_order_complete_extrusion'),

    # Extrusion Record
    path('orders/<int:order_pk>/extrusion/', ExtrusionRecordCreateView.as_view(), name='trial_extrusion_record_create'),

    # Color Matching BOM
    path('color-matching/', ColorPowderBOMListView.as_view(), name='trial_color_matching_list'),
    path('orders/<int:order_pk>/color-bom/', ColorPowderBOMFillView.as_view(), name='trial_color_powder_bom_fill'),

    # Sample Splits
    path('orders/<int:order_pk>/splits/', SampleSplitManageView.as_view(), name='trial_sample_split_manage'),

    # Mold Types
    path('molds/', MoldTypeListView.as_view(), name='trial_mold_type_list'),
    path('molds/add/', MoldTypeCreateView.as_view(), name='trial_mold_type_add'),
    path('molds/<int:pk>/edit/', MoldTypeUpdateView.as_view(), name='trial_mold_type_edit'),

    # Injection Molding Orders
    path('injection/', InjectionMoldingOrderListView.as_view(), name='trial_injection_list'),
    path('orders/<int:order_pk>/injection/create/', InjectionMoldingOrderCreateView.as_view(), name='trial_injection_create'),
    path('injection/<int:pk>/', InjectionMoldingOrderDetailView.as_view(), name='trial_injection_detail'),
    path('injection/<int:pk>/complete/', InjectionMoldingCompleteView.as_view(), name='trial_injection_complete'),

    # Testing Orders
    path('testing/', TestingOrderListView.as_view(), name='trial_testing_list'),
    path('testing/<int:pk>/', TestingOrderDetailView.as_view(), name='trial_testing_detail'),
    path('testing/<int:pk>/fill-results/', TestingOrderFillResultsView.as_view(), name='trial_testing_fill_results'),
    path('testing/<int:pk>/write-back/', TestingOrderWriteBackView.as_view(), name='trial_testing_write_back'),

    # Sample Inventory
    path('samples/', SampleInventoryListView.as_view(), name='trial_sample_inventory'),
    path('samples/<int:pk>/ship/', SampleInventoryShipView.as_view(), name='trial_sample_ship'),

    # TomSelect autocomplete APIs
    path('api/search/', TrialAutocompleteView.as_view(), name='trial_api_search'),
]
