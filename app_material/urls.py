from django.urls import path
from .views.Material import *
from .views.MaterialTds import *
from .views.MaterialType import *
from .views.Scenario import *
from .views.TestConfig import *
from .views.Characteristic import *
from common_utils.views import MaterialAutocompleteView

urlpatterns = [

    # 1. 材料库 (Material)
    path('materials/', MaterialListView.as_view(), name='material_list'),
    path('materials/add/', MaterialCreateView.as_view(), name='material_add'),
    path('materials/<int:pk>/', MaterialDetailView.as_view(), name='material_detail'),
    path('materials/<int:pk>/edit/', MaterialUpdateView.as_view(), name='material_edit'),
    path('materials/<int:pk>/export-tds/', MaterialTdsExportView.as_view(), name='material_export_tds'),

    # 【新增】批量发布/下架
    path('materials/bulk-publish/', MaterialBulkPublishView.as_view(), name='material_bulk_publish'),

    # 异步搜索 API (用于 TomSelect)
    path('api/search/', MaterialAutocompleteView.as_view(), name='material_api_search'),

    # 2. 材料特征属性 (MaterialCharacteristic)
    path('characteristics/', CharacteristicListView.as_view(), name='characteristic_list'),
    path('characteristics/add/', CharacteristicCreateView.as_view(), name='characteristic_add'),
    path('characteristics/<int:pk>/edit/', CharacteristicUpdateView.as_view(), name='characteristic_edit'),

    # 3. 材料类型 (MaterialType)
    path('types/', MaterialTypeListView.as_view(), name='type_list'),
    path('types/add/', MaterialTypeCreateView.as_view(), name='type_add'),
    path('types/<int:pk>/edit/', MaterialTypeUpdateView.as_view(), name='type_edit'),

    # 4. 应用场景 (ApplicationScenario)
    path('scenarios/', ScenarioListView.as_view(), name='scenario_list'),
    path('scenarios/add/', ScenarioCreateView.as_view(), name='scenario_add'),
    path('scenarios/<int:pk>/edit/', ScenarioUpdateView.as_view(), name='scenario_edit'),

    # 5. 测试标准配置 (TestConfig)
    path('test-configs/', TestConfigListView.as_view(), name='test_config_list'),
    path('test-configs/add/', TestConfigCreateView.as_view(), name='test_config_add'),
    path('test-configs/<int:pk>/edit/', TestConfigUpdateView.as_view(), name='test_config_edit'),

]
