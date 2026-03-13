from django.urls import path, include

urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('', include('ui.urls')),
    path('clusters/', include('clusters.urls')),
    path('master_slave_arch/', include('clusters.urls')),
    path('databases/', include('databases.urls')),
]
