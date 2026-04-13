from django.urls import path, include
from .views import catalog, download

app_name = 'app_catalog'

urlpatterns = [
    # 唯一入口：直接进入材料手册列表页 (仿官网"改性材料"页)
    path('', catalog.CatalogListView.as_view(), name='home'),
    path('search/', catalog.CatalogListView.as_view(), name='search'),
    
    # 详情页
    path('p/<int:pk>/', catalog.CatalogDetailView.as_view(), name='product_detail'),
    
    # 下载
    path('download/<int:pk>/<str:file_type>/', download.MaterialDownloadView.as_view(), name='material_download'),
    
    # Webhook API
    path('api/', include('app_catalog.api.urls')),
]
