from django.urls import path
from . import views

app_name = 'repayments'

urlpatterns = [
    path('instant-pay/', views.simulate_instant_pay_api, name='simulate_instant_pay'),
    path('upload-slip/', views.upload_payment_slip_view, name='upload_payment_slip'),
    path('<int:pk>/verify/', views.verify_receipt_api, name='verify_receipt'),
    path('<int:pk>/reject/', views.reject_receipt_api, name='reject_receipt'),
    path('<int:pk>/disburse/', views.disburse_loan_api, name='disburse_loan'),
]
