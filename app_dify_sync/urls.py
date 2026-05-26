from django.urls import path
from . import views

urlpatterns = [
    path('chatbot/', views.ChatbotView.as_view(), name='dify_chatbot'),
]
