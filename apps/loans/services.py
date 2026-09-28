from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum

from apps.repayments.services import (
    _add_months,
    generate_amortization_schedule,
    execute_disbursal,
    record_repayment,
    process_slip_upload,
    verify_repayment_receipt,
)
from apps.reports.services import (
    calculate_nbc_provisioning,
    calculate_delinquency_metrics,
    generate_report_csv,
)


def calculate_cbc_score(application):
    """
    Simulated Credit Bureau Cambodia (CBC) Underwriting Engine.
    Evaluates applicant DTI, collateral coverage, and adjusts baseline score.
    Returns calculated score, risk grade (A-D), ratios, and underwriting recommendation.
    """
    borrower = getattr(application, 'borrower', None)
    profile = getattr(borrower, 'borrower_profile', None) if borrower else None
    base_score = getattr(profile, 'credit_score', None) or 650

    income = getattr(application, 'monthly_income', None) or Decimal('0.00')
    emi = getattr(application, 'emi', None) or Decimal('0.00')
    if income > Decimal('0.00'):
        dti = ((emi / income) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        dti = Decimal('100.00')

    principal = getattr(application, 'amount', None) or Decimal('0.00')
    if getattr(application, 'id', None):
        total_collateral = application.collaterals.aggregate(
            total=Sum('estimated_valuation')
        )['total'] or Decimal('0.00')
    else:
        total_collateral = Decimal('0.00')

    if principal > Decimal('0.00'):
        ccr = ((total_collateral / principal) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    else:
        ccr = Decimal('0.00')

    if dti <= Decimal('30.00'):
        dti_adjustment = 20
    elif dti <= Decimal('40.00'):
        dti_adjustment = 0
    elif dti <= Decimal('50.00'):
        dti_adjustment = -20
    else:
        dti_adjustment = -40

    if ccr >= Decimal('150.00'):
        ccr_adjustment = 20
    elif ccr >= Decimal('100.00'):
        ccr_adjustment = 10
    elif ccr >= Decimal('50.00'):
        ccr_adjustment = 0
    else:
        ccr_adjustment = -10

    final_score = int(base_score + dti_adjustment + ccr_adjustment)
    final_score = max(300, min(850, final_score))

    if final_score >= 700:
        risk_grade = 'A'
        recommendation = 'អនុម័តដោយស្វ័យប្រវត្តិ / Highly Recommended - Low Credit Risk'
        recommendation_en = 'Highly Recommended - Low Credit Risk'
    elif final_score >= 620:
        risk_grade = 'B'
        recommendation = 'អនុម័តក្រោមលក្ខខណ្ឌ / Recommended with Standard Terms'
        recommendation_en = 'Recommended with Standard Terms'
    elif final_score >= 550:
        risk_grade = 'C'
        recommendation = 'ទាមទារការពិនិត្យបន្ថែម / Additional Collateral or Guarantor Required'
        recommendation_en = 'Additional Collateral or Guarantor Required'
    else:
        risk_grade = 'D'
        recommendation = 'បដិសេធ / High Risk - Recommended Rejection'
        recommendation_en = 'High Risk - Recommended Rejection'

    return {
        'cbc_score': final_score,
        'base_score': base_score,
        'risk_grade': risk_grade,
        'dti': dti,
        'collateral_coverage': ccr,
        'total_collateral': total_collateral,
        'recommendation': recommendation,
        'recommendation_en': recommendation_en,
    }


__all__ = [
    'calculate_cbc_score',
    '_add_months',
    'generate_amortization_schedule',
    'execute_disbursal',
    'record_repayment',
    'process_slip_upload',
    'verify_repayment_receipt',
    'calculate_nbc_provisioning',
    'calculate_delinquency_metrics',
    'generate_report_csv',
]
