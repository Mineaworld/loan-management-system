from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class LoanProduct(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Annual Interest Rate (%)")
    currency = models.CharField(max_length=3, choices=[('USD', 'USD'), ('KHR', 'KHR')], default='USD')
    min_amount = models.DecimalField(max_digits=14, decimal_places=2)
    max_amount = models.DecimalField(max_digits=14, decimal_places=2)
    min_tenure_months = models.IntegerField(default=6)
    max_tenure_months = models.IntegerField(default=36)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.interest_rate}% p.a. {self.currency})"

    def clean(self):
        if self.min_amount and self.max_amount and self.min_amount > self.max_amount:
            raise ValidationError({'min_amount': 'Min amount cannot exceed max amount.'})
        if self.min_tenure_months and self.max_tenure_months and self.min_tenure_months > self.max_tenure_months:
            raise ValidationError({'min_tenure_months': 'Min tenure cannot exceed max tenure.'})


class LoanApplication(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'សេចក្តីព្រាង / Draft'
        SUBMITTED = 'SUBMITTED', 'បានដាក់ពាក្យ / Submitted'
        UNDER_REVIEW = 'UNDER_REVIEW', 'កំពុងពិនិត្យ / Under Review'
        APPROVED = 'APPROVED', 'បានអនុម័ត / Approved'
        REJECTED = 'REJECTED', 'បានបដិសេធ / Rejected'
        DISBURSED = 'DISBURSED', 'បានបើកផ្តល់ / Disbursed'
        ACTIVE = 'ACTIVE', 'កំពុងសង / Active'
        COMPLETED = 'COMPLETED', 'បានទូទាត់រួចរាល់ / Completed'
        DEFAULTED = 'DEFAULTED', 'ហួសកំណត់ធ្ងន់ធ្ងរ / Defaulted'

    application_no = models.CharField(max_length=30, unique=True, db_index=True)
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='loan_applications')
    product = models.ForeignKey(LoanProduct, on_delete=models.PROTECT, related_name='applications')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, choices=[('USD', 'USD'), ('KHR', 'KHR')], default='USD')
    tenure_months = models.IntegerField()
    monthly_income = models.DecimalField(max_digits=14, decimal_places=2)
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_applications'
    )
    officer_remarks = models.TextField(blank=True, null=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def applicant_name(self):
        if self.borrower:
            return self.borrower.get_full_name() or self.borrower.username
        return ''

    def __str__(self):
        return f"{self.application_no} - {self.applicant_name} ({self.get_status_display()})"

    def clean(self):
        if self.product_id:
            if self.amount is not None:
                if self.amount < self.product.min_amount or self.amount > self.product.max_amount:
                    raise ValidationError({
                        'amount': f"Amount must be between {self.product.min_amount} and {self.product.max_amount} {self.product.currency}."
                    })
            if self.tenure_months is not None:
                if self.tenure_months < self.product.min_tenure_months or self.tenure_months > self.product.max_tenure_months:
                    raise ValidationError({
                        'tenure_months': f"Tenure must be between {self.product.min_tenure_months} and {self.product.max_tenure_months} months."
                    })

    def save(self, *args, **kwargs):
        if not self.application_no:
            from datetime import datetime
            prefix = f"LN-{datetime.now().strftime('%Y%m')}"
            count = LoanApplication.objects.filter(application_no__startswith=prefix).count() + 1
            candidate = f"{prefix}-{count:04d}"
            while LoanApplication.objects.filter(application_no=candidate).exists():
                count += 1
                candidate = f"{prefix}-{count:04d}"
            self.application_no = candidate
        super().save(*args, **kwargs)

    @property
    def emi(self):
        """Calculate Equal Monthly Installment using NBC Reducing Balance standard."""
        if not self.amount or not self.product or not self.tenure_months:
            return Decimal('0.00')
        p = Decimal(str(self.amount))
        annual_rate = Decimal(str(self.product.interest_rate))
        r = annual_rate / Decimal('1200')
        n = int(self.tenure_months)
        if n <= 0:
            return Decimal('0.00')
        if r == 0:
            val = p / Decimal(str(n))
        else:
            factor = (Decimal('1') + r) ** n
            val = p * (r * factor) / (factor - Decimal('1'))
        if self.currency == 'KHR':
            return val.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        return val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def total_repayable(self):
        if not self.tenure_months:
            return Decimal('0.00')
        return self.emi * self.tenure_months

    @property
    def total_interest(self):
        if not self.amount or not self.tenure_months or self.total_repayable <= 0:
            return Decimal('0.00')
        return self.total_repayable - self.amount


class Collateral(models.Model):
    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='collaterals')
    collateral_type = models.CharField(max_length=50)
    title_deed_number = models.CharField(max_length=100, blank=True, null=True)
    estimated_valuation = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.collateral_type} ({self.title_deed_number or 'No Title'}) - ${self.estimated_valuation}"


class ActionLog(models.Model):
    loan = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='action_logs')
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='loan_action_logs'
    )
    from_status = models.CharField(max_length=25)
    to_status = models.CharField(max_length=25)
    action_notes = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        actor = self.changed_by.username if self.changed_by else "System"
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.loan.application_no}: {self.from_status} -> {self.to_status} ({actor})"

from apps.repayments.models import LoanInstallment, PaymentReceipt

__all__ = [
    'LoanProduct',
    'LoanApplication',
    'Collateral',
    'ActionLog',
    'LoanInstallment',
    'PaymentReceipt',
]

