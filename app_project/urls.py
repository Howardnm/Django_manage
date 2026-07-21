from django.urls import path
from .views.Project import ProjectListView, ProjectCreateView, ProjectUpdateView, ProjectDetailView, ProjectFieldChangeDetailView
from .views.ProjectFormulaProcess import ProjectFormulaProcessView, CompetitorOrderCreateView, FormulaMeanWritebackView
from .views.ProjectNode import *
from .views.ProjectReport import ProjectReportExportView
from .views.ProjectMember import *
from .views.ProjectSalesMember import *
from .views.PerformanceRule import *
from .views.FailureReason import *
from .views.FeedbackType import *
from app_panel.views.PerformanceView import UserPerformanceListView, UserPerformanceDetailView
from app_form_management.views import ProjectFormListView

urlpatterns = [
    path('list/', ProjectListView.as_view(), name='project_list'),
    path('create/', ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('<int:pk>/formula-process/', ProjectFormulaProcessView.as_view(), name='project_formula_process'),
    path('<int:pk>/formula-process/competitor/create/', CompetitorOrderCreateView.as_view(), name='project_competitor_order_create'),
    path('<int:pk>/formula-process/mean-writeback/<int:formula_pk>/', FormulaMeanWritebackView.as_view(), name='project_formula_mean_writeback'),
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), name='project_edit'),
    path('field-change/<int:pk>/detail/', ProjectFieldChangeDetailView.as_view(), name='project_field_change_detail'),
    
    # 绩效相关
    path('performance/', UserPerformanceListView.as_view(), name='project_performance_list'),
    path('performance/user/<int:user_id>/', UserPerformanceDetailView.as_view(), name='project_performance_user_detail'), # 【新增】
    path('performance/rules/', NodeScoreRuleListView.as_view(), name='project_score_rule_list'),
    path('performance/rules/create/', NodeScoreRuleCreateView.as_view(), name='project_score_rule_create'),
    path('performance/rules/<int:pk>/edit/', NodeScoreRuleUpdateView.as_view(), name='project_score_rule_edit'),
    path('performance/rules/<int:pk>/delete/', NodeScoreRuleDeleteView.as_view(), name='project_score_rule_delete'),
    
    # 节点的更新路由
    path('node/<int:pk>/update/', ProjectNodeUpdateView.as_view(), name='node_update'),
    path('node/<int:pk>/failed/', NodeFailedView.as_view(), name='node_failed'),
    path('node/<int:pk>/feedback/', InsertFeedbackView.as_view(), name='node_feedback'),
    
    path('<int:pk>/forms/', ProjectFormListView.as_view(), name='project_form_list'),
    path('<int:pk>/export/', ProjectReportExportView.as_view(), name='project_export_report'),

    # 项目协同成员管理
    path('<int:pk>/member/manage/', ProjectMemberManageView.as_view(), name='project_member_manage'),
    path('member/<int:pk>/delete/', ProjectMemberDeleteView.as_view(), name='project_member_delete'),

    # 项目销售成员管理
    path('<int:pk>/sales-member/manage/', ProjectSalesMemberManageView.as_view(), name='project_sales_member_manage'),
    path('sales-member/<int:pk>/delete/', ProjectSalesMemberDeleteView.as_view(), name='project_sales_member_delete'),

    # 不合格原因管理
    path('failure-reasons/', FailureReasonListView.as_view(), name='failure_reason_list'),
    path('failure-reasons/create/', FailureReasonCreateView.as_view(), name='failure_reason_create'),
    path('failure-reasons/<int:pk>/edit/', FailureReasonUpdateView.as_view(), name='failure_reason_edit'),
    path('failure-reasons/<int:pk>/delete/', FailureReasonDeleteView.as_view(), name='failure_reason_delete'),

    # 客户意见类型管理
    path('feedback-types/', FeedbackTypeListView.as_view(), name='feedback_type_list'),
    path('feedback-types/create/', FeedbackTypeCreateView.as_view(), name='feedback_type_create'),
    path('feedback-types/<int:pk>/edit/', FeedbackTypeUpdateView.as_view(), name='feedback_type_edit'),
    path('feedback-types/<int:pk>/delete/', FeedbackTypeDeleteView.as_view(), name='feedback_type_delete'),
]
