from django.urls import path
from app_mold_injection.views.injection import (
    InjectionTaskListView, InjectionCreateView,
    InjectionCreateFromInventoryView, InjectionDetailView,
    InjectionStartView, InjectionCompleteView,
)
from app_mold_injection.views.mold import (
    MoldTypeListView, MoldTypeCreateView, MoldTypeUpdateView,
)

app_name = 'mold_injection'

urlpatterns = [
    # Injection tasks
    path('tasks/', InjectionTaskListView.as_view(), name='task_list'),
    path('tasks/<int:order_pk>/create/', InjectionCreateView.as_view(), name='task_create'),
    path('tasks/create-from-inventory/', InjectionCreateFromInventoryView.as_view(), name='task_create_from_inventory'),
    path('tasks/<int:pk>/', InjectionDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/start/', InjectionStartView.as_view(), name='task_start'),
    path('tasks/<int:pk>/complete/', InjectionCompleteView.as_view(), name='task_complete'),

    # Mold types
    path('molds/', MoldTypeListView.as_view(), name='mold_list'),
    path('molds/add/', MoldTypeCreateView.as_view(), name='mold_add'),
    path('molds/<int:pk>/edit/', MoldTypeUpdateView.as_view(), name='mold_edit'),
]
