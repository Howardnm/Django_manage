from django.urls import path
from .views.MachineModel import *
from .views.ScrewCombination import *
from .views.ProcessProfile import *

urlpatterns = [
    # 机台型号
    path('machines/', MachineModelListView.as_view(), name='process_machine_list'),
    path('machines/add/', MachineModelCreateView.as_view(), name='process_machine_add'),
    path('machines/<int:pk>/edit/', MachineModelUpdateView.as_view(), name='process_machine_edit'),

    # 螺杆组合
    path('screws/', ScrewCombinationListView.as_view(), name='process_screw_list'),
    path('screws/add/', ScrewCombinationCreateView.as_view(), name='process_screw_add'),
    path('screws/<int:pk>/edit/', ScrewCombinationUpdateView.as_view(), name='process_screw_edit'),

    # 工艺方案
    path('profiles/', ProcessProfileListView.as_view(), name='process_profile_list'),
    path('profiles/add/', ProcessProfileCreateView.as_view(), name='process_profile_add'),
    path('profiles/<int:pk>/', ProcessProfileDetailView.as_view(), name='process_profile_detail'),
    path('profiles/<int:pk>/edit/', ProcessProfileUpdateView.as_view(), name='process_profile_edit'),
]
