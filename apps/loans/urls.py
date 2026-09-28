from django.urls import path
from . import views

app_name = 'loans'

urlpatterns = [
    path('borrower/', views.borrower_portal_view, name='borrower_portal'),
    path('officer/', views.officer_dashboard_view, name='officer_dashboard'),
    path('applications/<int:pk>/status/', views.update_application_status_api, name='update_status_api'),
    path('applications/<int:pk>/cbc/', views.application_cbc_api, name='application_cbc_api'),
    path('applications/<int:pk>/disburse/', views.disburse_loan_api, name='disburse_loan_api'),
    path('repayments/instant-pay/', views.simulate_instant_pay_api, name='simulate_instant_pay'),
    path('repayments/upload-slip/', views.upload_payment_slip_view, name='upload_payment_slip'),
    path('repayments/<int:pk>/verify/', views.verify_receipt_api, name='verify_receipt'),
    path('repayments/<int:pk>/reject/', views.reject_receipt_api, name='reject_receipt'),
    path('reports/nbc-provisioning/', views.nbc_provisioning_api, name='nbc_provisioning_api'),
    path('reports/export-csv/', views.export_report_csv_view, name='export_report_csv'),
]
