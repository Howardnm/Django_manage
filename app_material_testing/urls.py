from django.urls import path
from app_material_testing.views import (
    TestingTaskListView, TestingTaskDetailView,
    FillResultsView, WriteBackView,
)

app_name = 'material_testing'

urlpatterns = [
    path('', TestingTaskListView.as_view(), name='list'),
    path('<int:pk>/', TestingTaskDetailView.as_view(), name='detail'),
    path('<int:pk>/fill-results/', FillResultsView.as_view(), name='fill'),
    path('<int:pk>/write-back/', WriteBackView.as_view(), name='writeback'),
]
