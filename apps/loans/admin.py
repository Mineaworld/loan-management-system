from django.contrib import admin
from .models import LoanProduct, LoanApplication, Collateral, ActionLog


@admin.register(LoanProduct)
class LoanProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'interest_rate', 'currency', 'min_amount', 'max_amount', 'is_active')
    list_filter = ('currency', 'is_active')
    search_fields = ('name', 'code')


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = ('application_no', 'borrower', 'product', 'branch', 'assigned_officer', 'amount', 'currency', 'tenure_months', 'status', 'created_at')
    list_filter = ('status', 'branch', 'currency', 'product')
    search_fields = ('application_no', 'borrower__username', 'borrower__first_name', 'borrower__last_name')


@admin.register(Collateral)
class CollateralAdmin(admin.ModelAdmin):
    list_display = ('loan', 'collateral_type', 'title_deed_number', 'estimated_valuation')
    search_fields = ('loan__application_no', 'title_deed_number', 'collateral_type')


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('loan', 'from_status', 'to_status', 'changed_by', 'timestamp')
    list_filter = ('from_status', 'to_status')
    search_fields = ('loan__application_no', 'changed_by__username')

