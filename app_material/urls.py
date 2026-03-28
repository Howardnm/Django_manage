from django.urls import path
from .views.Material import *
from .views.MaterialType import *
from .views.Scenario import *
from .views.TestConfig import *

urlpatterns = [

    # 材料库
    path('materials/', MaterialListView.as_view(), name='repo_material_list'),
    path('materials/add/', MaterialCreateView.as_view(), name='repo_material_add'),
    path('materials/<int:pk>/', MaterialDetailView.as_view(), name='repo_material_detail'),
    path('materials/<int:pk>/edit/', MaterialUpdateView.as_view(), name='repo_material_edit'),
    path('material/<int:material_id>/file/add/', MaterialFileUploadView.as_view(), name='repo_material_file_add'),
    path('material/file/<int:pk>/delete/', MaterialFileDeleteView.as_view(), name='repo_material_file_delete'),

    # 材料类型
    path('types/', MaterialTypeListView.as_view(), name='repo_type_list'),
    path('types/add/', MaterialTypeCreateView.as_view(), name='repo_type_add'),
    path('types/<int:pk>/edit/', MaterialTypeUpdateView.as_view(), name='repo_type_edit'),

    # 应用场景
    path('scenarios/', ScenarioListView.as_view(), name='repo_scenario_list'),
    path('scenarios/add/', ScenarioCreateView.as_view(), name='repo_scenario_add'),
    path('scenarios/<int:pk>/edit/', ScenarioUpdateView.as_view(), name='repo_scenario_edit'),

    # 测试标准配置
    path('test-configs/', TestConfigListView.as_view(), name='repo_test_config_list'),
    path('test-configs/add/', TestConfigCreateView.as_view(), name='repo_test_config_add'),
    path('test-configs/<int:pk>/edit/', TestConfigUpdateView.as_view(), name='repo_test_config_edit'),

]
