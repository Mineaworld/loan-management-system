from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, BorrowerProfile, OfficerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'email', 'role', 'phone_number', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Custom Profile Info', {'fields': ('role', 'phone_number', 'national_id', 'primary_currency')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Custom Profile Info', {'fields': ('role', 'phone_number', 'national_id', 'primary_currency')}),
    )


@admin.register(BorrowerProfile)
class BorrowerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'monthly_income', 'occupation', 'credit_score')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'occupation')


@admin.register(OfficerProfile)
class OfficerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'employee_id', 'branch', 'department', 'phone')
    search_fields = ('user__username', 'employee_id', 'branch')
