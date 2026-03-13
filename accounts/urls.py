from django.urls import path
from . import views

urlpatterns = [
    # 模板页面
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),
    path('register/', views.register_view, name='register'),

    # JSON API
    path('api/me/',                             views.MeView.as_view()),
    path('api/users/',                          views.UserListView.as_view()),
    path('api/users/<int:user_id>/',            views.UserDetailView.as_view()),
    path('api/groups/',                         views.GroupListView.as_view()),
    path('api/groups/<int:group_id>/',          views.GroupDetailView.as_view()),
    path('api/groups/<int:group_id>/members/',  views.GroupMemberView.as_view()),
    path('api/groups/<int:group_id>/members/<int:user_id>/', views.GroupMemberView.as_view()),
    path('api/groups/<int:group_id>/instances/', views.GroupInstanceView.as_view()),
]
