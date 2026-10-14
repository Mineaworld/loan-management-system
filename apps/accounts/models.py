from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Admin'
        OFFICER = 'OFFICER', 'Loan Officer'
        BORROWER = 'BORROWER', 'Borrower'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.BORROWER,
        db_index=True
    )
    phone_number = models.CharField(max_length=30, blank=True, null=True)
    national_id = models.CharField(max_length=50, blank=True, null=True)
    primary_currency = models.CharField(
        max_length=3,
        choices=[('USD', 'USD'), ('KHR', 'KHR')],
        default='USD'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        full_name = self.get_full_name()
        display_name = full_name if full_name.strip() else self.username
        return f"{display_name} ({self.get_role_display()})"

    @property
    def is_borrower(self):
        return self.role == self.Role.BORROWER

    @property
    def is_officer(self):
        return self.role == self.Role.OFFICER or self.is_superuser

    @property
    def is_admin_user(self):
        return self.role == self.Role.ADMIN or self.is_superuser


class Branch(models.Model):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name_km = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)
    province = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']
        verbose_name_plural = 'Branches'

    def __str__(self):
        return f"{self.name_km} ({self.name_en})"


class BorrowerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='borrower_profile')
    servicing_branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='borrowers')
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    occupation = models.CharField(max_length=150, blank=True, null=True)
    employer = models.CharField(max_length=150, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=50, blank=True, null=True)
    credit_score = models.IntegerField(default=720)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Borrower Profile: {self.user.username}"


class OfficerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='officer_profile')
    employee_id = models.CharField(max_length=50, blank=True, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='officers')
    department = models.CharField(max_length=100, default='Credit & Underwriting')
    phone = models.CharField(max_length=30, blank=True, null=True)
    desk_phone = models.CharField(max_length=30, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def branch_name(self):
        if self.branch:
            return self.branch.name_en
        return "Head Office - Phnom Penh"

    def __str__(self):
        branch_str = self.branch.name_en if self.branch else 'Unassigned'
        return f"Officer Profile: {self.user.username} ({self.employee_id or 'Staff'}) - {branch_str}"
