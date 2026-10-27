from django.urls import path

from .views import BomDetailView, BomListCreateView, MaterialNameView

urlpatterns = [
    path("materials/", MaterialNameView.as_view(), name="sap-material-names"),
    path("boms/", BomListCreateView.as_view(), name="sap-bom-list"),
    path(
        "boms/<str:matnr>/<str:werks>/<str:stlan>/<str:stlal>/",
        BomDetailView.as_view(),
        name="sap-bom-detail",
    ),
]
