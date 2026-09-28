from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('nbc-provisioning/', views.nbc_provisioning_api, name='nbc_provisioning'),
    path('export-csv/', views.export_report_csv_view, name='export_csv'),
]
