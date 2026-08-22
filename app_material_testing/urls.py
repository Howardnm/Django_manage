from django.urls import path
from app_material_testing.views import (
    TestingTaskListView, TestingTaskDetailView,
    FillResultsView, WriteBackView,
    ForceCompleteWriteBackView,
    TestingSampleListView,
)

app_name = 'material_testing'

urlpatterns = [
    path('', TestingTaskListView.as_view(), name='list'),
    path('<int:pk>/', TestingTaskDetailView.as_view(), name='detail'),
    path('<int:pk>/fill-results/', FillResultsView.as_view(), name='fill'),
    path('<int:pk>/write-back/', WriteBackView.as_view(), name='writeback'),
    path('<int:pk>/force-complete/', ForceCompleteWriteBackView.as_view(), name='force_complete'),

    # Sample inventory (testing scope: all SPECIMEN)
    path('specimens/', TestingSampleListView.as_view(), name='specimens'),
]
