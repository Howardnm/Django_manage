from django.urls import path
from .views.Project import *
from .views.ProjectNode import *
from .views.ProjectReport import ProjectReportExportView
from .views.ProjectMember import *
from .views.PerformanceRule import * # 【新增】
from app_panel.views.PerformanceView import UserPerformanceListView

urlpatterns = [
    path('list/', ProjectListView.as_view(), name='project_list'),
    path('create/', ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), name='project_edit'),
    
    # 绩效相关
    path('performance/', UserPerformanceListView.as_view(), name='project_performance_list'),
    path('performance/rules/', NodeScoreRuleListView.as_view(), name='project_score_rule_list'),
    path('performance/rules/create/', NodeScoreRuleCreateView.as_view(), name='project_score_rule_create'),
    path('performance/rules/<int:pk>/edit/', NodeScoreRuleUpdateView.as_view(), name='project_score_rule_edit'),
    path('performance/rules/<int:pk>/delete/', NodeScoreRuleDeleteView.as_view(), name='project_score_rule_delete'),
    
    # 节点的更新路由
    path('node/<int:pk>/update/', ProjectNodeUpdateView.as_view(), name='node_update'),
    path('node/<int:pk>/failed/', NodeFailedView.as_view(), name='node_failed'),
    path('node/<int:pk>/feedback/', InsertFeedbackView.as_view(), name='node_feedback'),
    
    path('<int:pk>/export/', ProjectReportExportView.as_view(), name='project_export_report'),

    # 项目协同成员管理
    path('<int:pk>/member/manage/', ProjectMemberManageView.as_view(), name='project_member_manage'),
    path('member/<int:pk>/delete/', ProjectMemberDeleteView.as_view(), name='project_member_delete'),
]
