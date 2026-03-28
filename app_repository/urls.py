from django.urls import path
from .views.ProjectRepository import *
from .views.Customer import *
from .views.OEM import *
from .views.Salesperson import *

urlpatterns = [
    # --- 基础数据管理主页 ---

    # 档案总览列表
    path('list/', ProjectRepositoryListView.as_view(), name='repo_list'),

    # 客户库
    path('customers/', CustomerListView.as_view(), name='repo_customer_list'),
    path('customers/add/', CustomerCreateView.as_view(), name='repo_customer_add'),
    path('customers/<int:pk>/', CustomerDetailView.as_view(), name='repo_customer_detail'),
    path('customers/<int:pk>/edit/', CustomerUpdateView.as_view(), name='repo_customer_edit'),

    # 项目档案
    path('project/<int:project_id>/edit/', ProjectRepositoryUpdateView.as_view(), name='repo_project_edit'),
    path('project/repo/<int:pk>/detail/', ProjectFileDetailView.as_view(), name='repo_project_file_detail'), # 【新增】资料详情页
    path('api/search/', RepoAutocompleteView.as_view(), name='repo_api_search'),
    path('repo/<int:repo_id>/file/add/', ProjectFileUploadView.as_view(), name='repo_file_add'),
    path('file/<int:pk>/delete/', ProjectFileDeleteView.as_view(), name='repo_file_delete'),

    # 业务员库
    path('sales/', SalespersonListView.as_view(), name='repo_sales_list'),
    path('sales/add/', SalespersonCreateView.as_view(), name='repo_sales_add'),
    path('sales/<int:pk>/', SalespersonDetailView.as_view(), name='repo_sales_detail'),
    path('sales/<int:pk>/edit/', SalespersonUpdateView.as_view(), name='repo_sales_edit'),

    # 主机厂 (OEM)
    path('oems/', OEMListView.as_view(), name='repo_oem_list'),
    path('oems/add/', OEMCreateView.as_view(), name='repo_oem_add'),
    path('oems/<int:pk>/', OEMDetailView.as_view(), name='repo_oem_detail'),
    path('oems/<int:pk>/edit/', OEMUpdateView.as_view(), name='repo_oem_edit'),
    path('oems/<int:pk>/file/form/', OEMStandardFileFormView.as_view(), name='repo_oem_file_form'), # 【新增】HTMX模态框
    path('oems/<int:pk>/file/upload/', OEMStandardFileUploadView.as_view(), name='repo_oem_file_upload'),
    path('oems/file/<int:pk>/delete/', OEMStandardFileDeleteView.as_view(), name='repo_oem_file_delete'),
]
