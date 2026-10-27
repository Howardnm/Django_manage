from django.urls import path

from .views import FinishedBomListView, FinishedBomPlantListView, FinishedBomPublishView

urlpatterns = [
    path("finished-boms/plants/", FinishedBomPlantListView.as_view(), name="finished-bom-plants"),
    path("finished-boms/publish/", FinishedBomPublishView.as_view(), name="finished-bom-publish"),
    path("finished-boms/", FinishedBomListView.as_view(), name="finished-bom-list"),
]
