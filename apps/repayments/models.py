from django.conf import settings
from django.db import models
from apps.loans.models import LoanApplication


class LoanInstallment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'រង់ចាំបង់ / Pending'
        PAID = 'PAID', 'បានបង់ / Paid'
        OVERDUE = 'OVERDUE', 'ហួសកាលកំណត់ / Overdue'
        VERIFYING = 'VERIFYING', 'កំពុងផ្ទៀងផ្ទាត់ / Verifying'

    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='installments')
    sequence_number = models.PositiveIntegerField()
    due_date = models.DateField(db_index=True)
    total_installment_emi = models.DecimalField(max_digits=14, decimal_places=2)
    principal_component = models.DecimalField(max_digits=14, decimal_places=2)
    interest_component = models.DecimalField(max_digits=14, decimal_places=2)
    remaining_balance = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'loans_loaninstallment'
        ordering = ['sequence_number']
        unique_together = ('loan', 'sequence_number')

    def __str__(self):
        return f"{self.loan.application_no} - #{self.sequence_number} ({self.due_date}): ${self.total_installment_emi} [{self.get_status_display()}]"


class PaymentReceipt(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'រង់ចាំផ្ទៀងផ្ទាត់ / Pending Verification'
        VERIFIED = 'VERIFIED', 'បានផ្ទៀងផ្ទាត់ / Verified'
        REJECTED = 'REJECTED', 'បានបដិសេធ / Rejected'

    class PaymentMethod(models.TextChoices):
        BAKONG_KHQR = 'BAKONG_KHQR', 'Bakong KHQR'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        CASH = 'CASH', 'Cash Counter'

    installment = models.ForeignKey(
        LoanInstallment,
        on_delete=models.CASCADE,
        related_name='payment_receipts'
    )
    loan = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name='payment_receipts'
    )
    payer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='submitted_receipts'
    )
    transaction_reference = models.CharField(max_length=64, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=5, default='USD')
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BAKONG_KHQR
    )
    slip_image = models.FileField(upload_to='payment_slips/%Y/%m/', null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_receipts'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    officer_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'loans_paymentreceipt'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_reference} - ${self.amount} [{self.get_status_display()}]"
