from django.urls import path
from .views.Material import *
from .views.MaterialType import *
from .views.Scenario import *
from .views.TestConfig import *
from .views.utils import MaterialAutocompleteView # 导入工具视图

urlpatterns = [

    # 材料库 (Material)
    path('materials/', MaterialListView.as_view(), name='material_list'),
    path('materials/add/', MaterialCreateView.as_view(), name='material_add'),
    path('materials/<int:pk>/', MaterialDetailView.as_view(), name='material_detail'),
    path('materials/<int:pk>/edit/', MaterialUpdateView.as_view(), name='material_edit'),
    path('material/<int:material_id>/file/add/', MaterialFileUploadView.as_view(), name='material_file_add'),
    path('material/file/<int:pk>/delete/', MaterialFileDeleteView.as_view(), name='material_file_delete'),

    # 异步搜索 API (用于 TomSelect)
    path('api/search/', MaterialAutocompleteView.as_view(), name='material_api_search'),

    # 材料类型 (MaterialType)
    path('types/', MaterialTypeListView.as_view(), name='type_list'),
    path('types/add/', MaterialTypeCreateView.as_view(), name='type_add'),
    path('types/<int:pk>/edit/', MaterialTypeUpdateView.as_view(), name='type_edit'),

    # 应用场景 (ApplicationScenario)
    path('scenarios/', ScenarioListView.as_view(), name='scenario_list'),
    path('scenarios/add/', ScenarioCreateView.as_view(), name='scenario_add'),
    path('scenarios/<int:pk>/edit/', ScenarioUpdateView.as_view(), name='scenario_edit'),

    # 测试标准配置 (TestConfig)
    path('test-configs/', TestConfigListView.as_view(), name='test_config_list'),
    path('test-configs/add/', TestConfigCreateView.as_view(), name='test_config_add'),
    path('test-configs/<int:pk>/edit/', TestConfigUpdateView.as_view(), name='test_config_edit'),

]
