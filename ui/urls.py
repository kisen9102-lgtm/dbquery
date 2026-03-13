from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='ui_index'),
    path('sql_editor/', views.sql_editor, name='sql_editor'),
]
