from django.urls import path
from .views.ProjectRepository import *
from .views.Material import *
from .views.MaterialType import *
from .views.Customer import *
from .views.OEM import *
from .views.Scenario import *
from .views.Salesperson import *
from common_utils.SecureFileDownload import *
from .views.TestConfig import *  # 【新增】
from debug_toolbar.toolbar import debug_toolbar_urls # 这是debug_toolbar的配置

urlpatterns = [
    # --- 基础数据管理主页 ---

    # 档案总览列表
    path('list/', ProjectRepositoryListView.as_view(), name='repo_list'),

    # 客户库
    path('customers/', CustomerListView.as_view(), name='repo_customer_list'),
    path('customers/add/', CustomerCreateView.as_view(), name='repo_customer_add'),
    path('customers/<int:pk>/edit/', CustomerUpdateView.as_view(), name='repo_customer_edit'),

    # 材料库
    path('materials/', MaterialListView.as_view(), name='repo_material_list'),
    path('materials/add/', MaterialCreateView.as_view(), name='repo_material_add'),
    path('materials/<int:pk>/', MaterialDetailView.as_view(), name='repo_material_detail'),
    path('materials/<int:pk>/edit/', MaterialUpdateView.as_view(), name='repo_material_edit'),
    path('material/<int:material_id>/file/add/', MaterialFileUploadView.as_view(), name='repo_material_file_add'),
    path('material/file/<int:pk>/delete/', MaterialFileDeleteView.as_view(), name='repo_material_file_delete'),

    # 项目档案
    path('project/<int:project_id>/edit/', ProjectRepositoryUpdateView.as_view(), name='repo_project_edit'),
    path('api/search/', RepoAutocompleteView.as_view(), name='repo_api_search'),
    path('repo/<int:repo_id>/file/add/', ProjectFileUploadView.as_view(), name='repo_file_add'),
    path('file/<int:pk>/delete/', ProjectFileDeleteView.as_view(), name='repo_file_delete'),

    # 材料类型
    path('types/', MaterialTypeListView.as_view(), name='repo_type_list'),
    path('types/add/', MaterialTypeCreateView.as_view(), name='repo_type_add'),
    path('types/<int:pk>/edit/', MaterialTypeUpdateView.as_view(), name='repo_type_edit'),

    # 应用场景
    path('scenarios/', ScenarioListView.as_view(), name='repo_scenario_list'),
    path('scenarios/add/', ScenarioCreateView.as_view(), name='repo_scenario_add'),
    path('scenarios/<int:pk>/edit/', ScenarioUpdateView.as_view(), name='repo_scenario_edit'),

    # 【新增】测试标准配置
    path('test-configs/', TestConfigListView.as_view(), name='repo_test_config_list'),
    path('test-configs/add/', TestConfigCreateView.as_view(), name='repo_test_config_add'),
    path('test-configs/<int:pk>/edit/', TestConfigUpdateView.as_view(), name='repo_test_config_edit'),

    # 通用下载路由
    path('download/<str:app_label>/<str:model_name>/<int:pk>/<str:field_name>/', SecureFileDownloadView.as_view(), name='secure_download'),

    # 业务员库
    path('sales/', SalespersonListView.as_view(), name='repo_sales_list'),
    path('sales/add/', SalespersonCreateView.as_view(), name='repo_sales_add'),
    path('sales/<int:pk>/edit/', SalespersonUpdateView.as_view(), name='repo_sales_edit'),

    # 主机厂 (OEM)
    path('oems/', OEMListView.as_view(), name='repo_oem_list'),
    path('oems/add/', OEMCreateView.as_view(), name='repo_oem_add'),
    path('oems/<int:pk>/edit/', OEMUpdateView.as_view(), name='repo_oem_edit'),
] + debug_toolbar_urls() # 这是debug_toolbar的配置