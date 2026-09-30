from django.urls import path

from . import views

urlpatterns = [
    path('', views.QuotationListView.as_view(), name='quotation_list'),
    path('create/', views.QuotationCreateView.as_view(), name='quotation_create'),
    path('<int:pk>/edit/', views.QuotationEditView.as_view(), name='quotation_edit'),
    path('<int:pk>/', views.QuotationDetailView.as_view(), name='quotation_detail'),
    path('<int:pk>/action/', views.QuotationStepActionView.as_view(), name='quotation_step_action'),
    path('<int:pk>/return/', views.QuotationReturnView.as_view(), name='quotation_return'),
    path('<int:pk>/reassign/', views.QuotationReassignView.as_view(), name='quotation_reassign'),
    path('<int:pk>/print/', views.QuotationPrintView.as_view(), name='quotation_print'),
]
