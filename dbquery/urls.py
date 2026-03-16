from django.urls import path, include

urlpatterns = [
    path('accounts/', include('accounts.urls')),
    path('', include('ui.urls')),
path('databases/', include('databases.urls')),
]
