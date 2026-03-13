from django.urls import path
from . import views

urlpatterns = [
    path('query_arch/', views.QueryArchView.as_view(), name='query_arch'),
]
