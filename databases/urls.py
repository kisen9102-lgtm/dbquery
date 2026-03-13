from django.urls import path
from . import views

urlpatterns = [
    path('', views.DatabaseListView.as_view(), name='db_names'),
    path('tables/', views.TableListView.as_view(), name='db_tables'),
    path('execute_sql/', views.ExecuteSqlView.as_view(), name='execute_sql'),
    path('instances/', views.InstanceListView.as_view(), name='instance_list'),
    path('instances/<int:pk>/', views.InstanceDetailView.as_view(), name='instance_detail'),
    path('search/', views.DatabaseSearchView.as_view(), name='db_search'),
]
