from django.urls import path
from app_panel.views import *

urlpatterns = [
    path('', IndexView.as_view(), name='home'),
]