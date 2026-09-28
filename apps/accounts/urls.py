from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('auth/', views.UnifiedAuthView.as_view(), name='auth'),
    path('login/', views.UnifiedAuthView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('redirect/', views.role_redirect_view, name='role_redirect'),
    path('staff/create/', views.create_staff_view, name='create_staff'),
    path('staff/<int:pk>/edit/', views.edit_staff_view, name='edit_staff'),
    path('staff/<int:pk>/toggle-status/', views.toggle_user_status_view, name='toggle_user_status'),
    path('staff/<int:pk>/details/', views.get_user_details_api, name='staff_details'),
]
