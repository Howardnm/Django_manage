from django.urls import path
from .views.Project import *
from .views.ProjectNode import *

urlpatterns = [
    path('list/', ProjectListView.as_view(), name='project_list'),
    path('create/', ProjectCreateView.as_view(), name='project_create'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='project_detail'),
    path('<int:pk>/edit/', ProjectUpdateView.as_view(), name='project_edit'),
    # 关键：节点的更新路由
    path('node/<int:pk>/update/', ProjectNodeUpdateView.as_view(), name='node_update'),
    # 【新增】节点失败/返工 (对应 NodeFailedView)
    path('node/<int:pk>/failed/', NodeFailedView.as_view(), name='node_failed'),
    # 【新增】客户干预 (对应 InsertFeedbackView)
    path('node/<int:pk>/feedback/', InsertFeedbackView.as_view(), name='node_feedback'),
]
