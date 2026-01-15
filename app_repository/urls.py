from django.urls import path
from .views import *

urlpatterns = [
    # --- 基础数据管理主页 ---
    # 客户库
    path('customers/', CustomerListView.as_view(), name='repo_customer_list'),
    path('customers/add/', CustomerCreateView.as_view(), name='repo_customer_add'),
    path('customers/<int:pk>/edit/', CustomerUpdateView.as_view(), name='repo_customer_edit'),

    # 材料库
    path('materials/', MaterialListView.as_view(), name='repo_material_list'),
    path('materials/add/', MaterialCreateView.as_view(), name='repo_material_add'),
    # 【新增】详情页 (注意放在 edit 之前或者之后都可以，只要不冲突)
    path('materials/<int:pk>/', MaterialDetailView.as_view(), name='repo_material_detail'),
    path('materials/<int:pk>/edit/', MaterialUpdateView.as_view(), name='repo_material_edit'),

    # 项目档案 (入口是 project_id)
    path('project/<int:project_id>/edit/', ProjectRepositoryUpdateView.as_view(), name='repo_project_edit'),
    # 【新增】文件管理路由
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
]