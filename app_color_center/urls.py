from django.urls import path
from app_color_center.views import (
    TaskListView, ProjectListPageView, ProjectColorView,
)

app_name = 'color_center'

urlpatterns = [
    path('', TaskListView.as_view(), name='list'),
    path('projects/', ProjectListPageView.as_view(), name='project_list'),
    path('project/<int:project_pk>/', ProjectColorView.as_view(), name='project'),
]
