from django.urls import path
from .views import (
    WorkflowDefinitionListView,
    WorkflowEditorView,
    WorkflowSaveView,
    WorkflowDefinitionDeleteView,
    WorkflowToggleActiveView,
    MyTaskListView,
    CompletedTaskListView,
    InitiatedInstanceListView,
    WorkflowInstanceDetailView,
    TaskClaimView,
    TaskReassignView,
    TaskReturnView,
    WorkflowCancelView,
)

urlpatterns = [
    # 流程定义
    path('definitions/', WorkflowDefinitionListView.as_view(), name='workflow_definition_list'),
    path('editor/', WorkflowEditorView.as_view(), name='workflow_editor_create'),
    path('editor/<int:pk>/', WorkflowEditorView.as_view(), name='workflow_editor_edit'),
    path('save/', WorkflowSaveView.as_view(), name='workflow_save'),
    path('definition/<int:pk>/delete/', WorkflowDefinitionDeleteView.as_view(), name='workflow_definition_delete'),
    path('definition/<int:pk>/toggle_active/', WorkflowToggleActiveView.as_view(), name='workflow_toggle_active'),

    # 任务与实例
    path('tasks/', MyTaskListView.as_view(), name='workflow_my_tasks'),
    path('tasks/completed/', CompletedTaskListView.as_view(), name='workflow_completed_tasks'),
    path('initiated/', InitiatedInstanceListView.as_view(), name='workflow_initiated_list'),
    path('task/<int:pk>/claim/', TaskClaimView.as_view(), name='workflow_task_claim'),
    path('task/<int:pk>/reassign/', TaskReassignView.as_view(), name='workflow_task_reassign'),
    path('task/<int:pk>/return/', TaskReturnView.as_view(), name='workflow_task_return'),
    path('instance/<int:pk>/', WorkflowInstanceDetailView.as_view(), name='workflow_instance_detail'),
    path('instance/<int:pk>/cancel/', WorkflowCancelView.as_view(), name='workflow_cancel'),
]
