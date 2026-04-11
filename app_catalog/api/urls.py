from django.urls import path
from . import views

app_name = 'app_catalog_api'

urlpatterns = [
    # Webhook 接收端点
    path('webhook/material/', views.material_webhook_receiver, name='material_webhook'),
]
