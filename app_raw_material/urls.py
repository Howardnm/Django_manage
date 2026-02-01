from django.urls import path
from .views.Supplier import *
from .views.RawMaterialType import *
from .views.RawMaterial import *
from .views.api import raw_material_api_search # 导入新的 API 视图

urlpatterns = [
    # 供应商
    path('suppliers/', SupplierListView.as_view(), name='raw_supplier_list'),
    path('suppliers/add/', SupplierCreateView.as_view(), name='raw_supplier_add'),
    path('suppliers/<int:pk>/edit/', SupplierUpdateView.as_view(), name='raw_supplier_edit'),

    # 原材料类型
    path('types/', RawMaterialTypeListView.as_view(), name='raw_type_list'),
    path('types/add/', RawMaterialTypeCreateView.as_view(), name='raw_type_add'),
    path('types/<int:pk>/edit/', RawMaterialTypeUpdateView.as_view(), name='raw_type_edit'),

    # 原材料
    path('materials/', RawMaterialListView.as_view(), name='raw_material_list'),
    path('materials/add/', RawMaterialCreateView.as_view(), name='raw_material_add'),
    path('materials/<int:pk>/', RawMaterialDetailView.as_view(), name='raw_material_detail'),
    path('materials/<int:pk>/edit/', RawMaterialUpdateView.as_view(), name='raw_material_edit'),
    # 【新增】复制副本路由
    path('materials/<int:pk>/duplicate/', RawMaterialDuplicateView.as_view(), name='raw_material_duplicate'),

    # 【新增】API 搜索路由 (用于 Tom Select 远程加载)
    path('api/search/', raw_material_api_search, name='raw_material_api_search'),
]
