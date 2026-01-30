from django.urls import path
from .views import (
    ResearchProjectListView,
    ResearchProjectCreateView,
    ResearchProjectUpdateView,
    ResearchProjectDetailView,
    ResearchProjectNodeUpdateView,
    ResearchNodeFailedView,
    ResearchProjectFileUploadView,
    ResearchProjectFileDeleteView
)

urlpatterns = [
    path('list/', ResearchProjectListView.as_view(), name='basic_research_list'),
    path('create/', ResearchProjectCreateView.as_view(), name='basic_research_create'),
    path('<int:pk>/', ResearchProjectDetailView.as_view(), name='basic_research_detail'),
    path('<int:pk>/edit/', ResearchProjectUpdateView.as_view(), name='basic_research_edit'),
    
    # 节点操作路由
    path('node/<int:pk>/update/', ResearchProjectNodeUpdateView.as_view(), name='basic_research_node_update'),
    path('node/<int:pk>/failed/', ResearchNodeFailedView.as_view(), name='basic_research_node_failed'),
    
    # 附件操作路由
    path('<int:pk>/upload/', ResearchProjectFileUploadView.as_view(), name='basic_research_file_upload'),
    path('file/<int:pk>/delete/', ResearchProjectFileDeleteView.as_view(), name='basic_research_file_delete'),
]
