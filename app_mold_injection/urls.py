from django.urls import path
from app_mold_injection.views.injection import (
    InjectionTaskListView, InjectionDetailView,
    InjectionCompleteView,
)
from app_mold_injection.views.mold import (
    MoldTypeListView, MoldTypeCreateView, MoldTypeUpdateView,
)
app_name = 'mold_injection'

urlpatterns = [
    # Injection tasks
    path('tasks/', InjectionTaskListView.as_view(), name='task_list'),
    path('tasks/<int:pk>/', InjectionDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/complete/', InjectionCompleteView.as_view(), name='task_complete'),

    # Mold types
    path('molds/', MoldTypeListView.as_view(), name='mold_list'),
    path('molds/add/', MoldTypeCreateView.as_view(), name='mold_add'),
    path('molds/<int:pk>/edit/', MoldTypeUpdateView.as_view(), name='mold_edit'),

]
