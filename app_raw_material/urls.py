from django.urls import path
from .views.Supplier import *
from .views.RawMaterialType import *
from .views.RawMaterial import *

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
]
