from django.urls import path

from . import views

app_name = 'app_catalog'

urlpatterns = [
    path('', views.CatalogListView.as_view(), name='home'),
    path('search/', views.CatalogListView.as_view(), name='search'),
    path('p/<int:pk>/', views.CatalogDetailView.as_view(), name='product_detail'),
    path('login/', views.MemberLoginView.as_view(), name='login'),
    path('logout/', views.MemberLogoutView.as_view(), name='logout'),
    path('download/<int:pk>/<str:file_type>/', views.MaterialDownloadView.as_view(), name='material_download'),
]
