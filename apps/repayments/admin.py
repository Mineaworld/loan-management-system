from django.contrib import admin
from .models import LoanInstallment, PaymentReceipt


@admin.register(LoanInstallment)
class LoanInstallmentAdmin(admin.ModelAdmin):
    list_display = ('loan', 'sequence_number', 'due_date', 'total_installment_emi', 'remaining_balance', 'status', 'paid_at')
    list_filter = ('status', 'due_date')
    search_fields = ('loan__application_no', 'loan__borrower__username')


@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ('transaction_reference', 'loan', 'amount', 'currency', 'payment_method', 'status', 'verified_by', 'created_at')
    list_filter = ('status', 'payment_method', 'currency')
    search_fields = ('transaction_reference', 'loan__application_no', 'payer__username')
