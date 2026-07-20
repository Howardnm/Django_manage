from django.urls import path
from .views.ProjectRepository import *
from .views.Customer import *
from .views.OEM import *
from .views.GradeFactor import * # 【新增】

urlpatterns = [
    # --- 基础数据管理主页 ---

    # 客户库 (用户画像管理)
    path('customers/', CustomerListView.as_view(), name='repo_customer_list'),
    path('customers/add/', CustomerCreateView.as_view(), name='repo_customer_add'),
    path('customers/<int:pk>/', CustomerDetailView.as_view(), name='repo_customer_detail'),
    path('customers/<int:pk>/edit/', CustomerUpdateView.as_view(), name='repo_customer_edit'),
    path('customers/ranking/', CustomerRankingView.as_view(), name='repo_customer_ranking'),

    # 项目档案 (核心业务)
    path('project/<int:project_id>/edit/', ProjectRepositoryUpdateView.as_view(), name='repo_project_edit'),
    path('project/repo/<int:pk>/detail/', ProjectFileDetailView.as_view(), name='repo_project_file_detail'),
    path('change/<int:pk>/detail/', RepoFieldChangeModalView.as_view(), name='repo_field_change_detail'),
    path('api/search/', RepoAutocompleteView.as_view(), name='repo_api_search'),

    # 主机厂 (OEM 用户画像管理)
    path('oems/', OEMListView.as_view(), name='repo_oem_list'),
    path('oems/add/', OEMCreateView.as_view(), name='repo_oem_add'),
    path('oems/<int:pk>/', OEMDetailView.as_view(), name='repo_oem_detail'),
    path('oems/<int:pk>/edit/', OEMUpdateView.as_view(), name='repo_oem_edit'),

    # 等级因子管理 (绩效规则扩展) 【新增】
    path('performance/grade-factors/', GradeFactorListView.as_view(), name='repo_grade_factor_list'),
    path('performance/grade-factors/create/', GradeFactorCreateView.as_view(), name='repo_grade_factor_create'),
    path('performance/grade-factors/<int:pk>/edit/', GradeFactorUpdateView.as_view(), name='repo_grade_factor_edit'),
    path('performance/grade-factors/<int:pk>/delete/', GradeFactorDeleteView.as_view(), name='repo_grade_factor_delete'),
]
