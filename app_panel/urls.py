from django.urls import path
from .views import PanelIndexView

urlpatterns = [
    path('', PanelIndexView.as_view(), name='panel_index'),
]