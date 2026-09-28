import csv
import io
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

from apps.loans.models import LoanApplication
from apps.repayments.models import LoanInstallment, PaymentReceipt


def calculate_nbc_provisioning(queryset=None):
    if queryset is None:
        queryset = LoanApplication.objects.filter(
            status__in=[
                LoanApplication.Status.ACTIVE,
                LoanApplication.Status.DISBURSED
            ]
        ).select_related('borrower', 'product').prefetch_related('installments')

    today = timezone.now().date()

    tiers = [
        {
            'tier_key': 'NORMAL',
            'name_km': 'ឥណទានធម្មតា (Standard)',
            'name_en': 'Normal (Standard)',
            'dpd_range': '0 - 29 ថ្ងៃ / Days',
            'dpd_km': '0 - 29 ថ្ងៃ',
            'dpd_en': '0 - 29 Days',
            'rate_pct': Decimal('1.0'),
            'rate': Decimal('0.01'),
            'loan_count': 0,
            'total_balance': Decimal('0.00'),
            'required_provision': Decimal('0.00'),
        },
        {
            'tier_key': 'SPECIAL_MENTION',
            'name_km': 'ឥណទានត្រូវតាមដានពិសេស (Special Mention)',
            'name_en': 'Special Mention',
            'dpd_range': '30 - 89 ថ្ងៃ / Days',
            'dpd_km': '30 - 89 ថ្ងៃ',
            'dpd_en': '30 - 89 Days',
            'rate_pct': Decimal('3.0'),
            'rate': Decimal('0.03'),
            'loan_count': 0,
            'total_balance': Decimal('0.00'),
            'required_provision': Decimal('0.00'),
        },
        {
            'tier_key': 'SUBSTANDARD',
            'name_km': 'ឥណទានក្រោមបទដ្ឋាន (Substandard)',
            'name_en': 'Substandard',
            'dpd_range': '90 - 179 ថ្ងៃ / Days',
            'dpd_km': '90 - 179 ថ្ងៃ',
            'dpd_en': '90 - 179 Days',
            'rate_pct': Decimal('20.0'),
            'rate': Decimal('0.20'),
            'loan_count': 0,
            'total_balance': Decimal('0.00'),
            'required_provision': Decimal('0.00'),
        },
        {
            'tier_key': 'DOUBTFUL',
            'name_km': 'ឥណទានសង្ស័យ (Doubtful)',
            'name_en': 'Doubtful',
            'dpd_range': '180 - 359 ថ្ងៃ / Days',
            'dpd_km': '180 - 359 ថ្ងៃ',
            'dpd_en': '180 - 359 Days',
            'rate_pct': Decimal('50.0'),
            'rate': Decimal('0.50'),
            'loan_count': 0,
            'total_balance': Decimal('0.00'),
            'required_provision': Decimal('0.00'),
        },
        {
            'tier_key': 'LOSS',
            'name_km': 'ឥណទានខាតបង់ (Loss)',
            'name_en': 'Loss',
            'dpd_range': '≥ 360 ថ្ងៃ / Days',
            'dpd_km': '≥ 360 ថ្ងៃ',
            'dpd_en': '≥ 360 Days',
            'rate_pct': Decimal('100.0'),
            'rate': Decimal('1.00'),
            'loan_count': 0,
            'total_balance': Decimal('0.00'),
            'required_provision': Decimal('0.00'),
        },
    ]

    tier_map = {t['tier_key']: t for t in tiers}
    total_portfolio = Decimal('0.00')
    total_provision = Decimal('0.00')
    total_loans = 0
    loan_details = []

    for loan in queryset:
        insts = list(loan.installments.all())
        unpaid_insts = [i for i in insts if i.status != LoanInstallment.Status.PAID]
        if not unpaid_insts:
            continue

        outstanding = sum((i.principal_component for i in unpaid_insts), Decimal('0.00'))
        if outstanding <= Decimal('0.00'):
            outstanding = loan.amount

        overdue_days = [
            (today - i.due_date).days
            for i in unpaid_insts
            if i.due_date < today
        ]
        dpd = max(overdue_days) if overdue_days else 0

        if dpd >= 360:
            assigned_key = 'LOSS'
        elif dpd >= 180:
            assigned_key = 'DOUBTFUL'
        elif dpd >= 90:
            assigned_key = 'SUBSTANDARD'
        elif dpd >= 30:
            assigned_key = 'SPECIAL_MENTION'
        else:
            assigned_key = 'NORMAL'

        target_tier = tier_map[assigned_key]
        target_tier['loan_count'] += 1
        target_tier['total_balance'] += outstanding

        total_portfolio += outstanding
        total_loans += 1

        loan_details.append({
            'loan_id': loan.id,
            'application_no': loan.application_no,
            'borrower_name': loan.applicant_name,
            'product_name': loan.product.name,
            'currency': loan.currency,
            'outstanding': outstanding,
            'dpd': dpd,
            'tier_key': assigned_key,
            'tier_name': target_tier['name_en'],
        })

    for t in tiers:
        t['required_provision'] = (t['total_balance'] * t['rate']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        total_provision += t['required_provision']

    return {
        'tiers': tiers,
        'total_loans': total_loans,
        'total_portfolio': total_portfolio,
        'total_provision': total_provision,
        'loan_details': loan_details,
    }


def calculate_delinquency_metrics(queryset=None):
    prov_data = calculate_nbc_provisioning(queryset)
    total_portfolio = prov_data['total_portfolio']
    total_loans = prov_data['total_loans']

    par_30_balance = sum((
        t['total_balance'] for t in prov_data['tiers']
        if t['tier_key'] in ['SPECIAL_MENTION', 'SUBSTANDARD', 'DOUBTFUL', 'LOSS']
    ), Decimal('0.00'))

    par_90_balance = sum((
        t['total_balance'] for t in prov_data['tiers']
        if t['tier_key'] in ['SUBSTANDARD', 'DOUBTFUL', 'LOSS']
    ), Decimal('0.00'))

    par_30_ratio = ((par_30_balance / total_portfolio) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if total_portfolio > Decimal('0.00') else Decimal('0.00')
    par_90_ratio = ((par_90_balance / total_portfolio) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if total_portfolio > Decimal('0.00') else Decimal('0.00')

    all_installments = LoanInstallment.objects.filter(
        loan__status__in=[LoanApplication.Status.ACTIVE, LoanApplication.Status.DISBURSED]
    )
    today = timezone.now().date()
    due_to_date = all_installments.filter(due_date__lte=today)
    total_due_count = due_to_date.count()
    paid_count = due_to_date.filter(status=LoanInstallment.Status.PAID).count()
    collection_rate = round((paid_count / total_due_count * 100), 1) if total_due_count > 0 else 100.0

    return {
        'total_portfolio': total_portfolio,
        'total_loans': total_loans,
        'par_30_balance': par_30_balance,
        'par_30_ratio': float(par_30_ratio),
        'par_90_balance': par_90_balance,
        'par_90_ratio': float(par_90_ratio),
        'collection_rate': collection_rate,
        'total_due_count': total_due_count,
        'paid_count': paid_count,
        'tiers': prov_data['tiers'],
        'total_provision': prov_data['total_provision'],
    }


def generate_report_csv(report_type='asset_quality'):
    buffer = io.StringIO()
    buffer.write('\ufeff')
    writer = csv.writer(buffer)

    if report_type == 'asset_quality':
        prov = calculate_nbc_provisioning()
        writer.writerow(['NATIONAL BANK OF CAMBODIA (NBC) - STATUTORY ASSET QUALITY & PROVISIONING REPORT'])
        writer.writerow(['Generated At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['Total Portfolio Balance (USD)', f"{prov['total_portfolio']:.2f}"])
        writer.writerow(['Total Required Capital Provision (USD)', f"{prov['total_provision']:.2f}"])
        writer.writerow([])
        writer.writerow([
            'NBC Classification Tier',
            'Khmer Designation',
            'Days Past Due (DPD)',
            'Loan Count',
            'Outstanding Principal (USD)',
            'Provisioning Rate (%)',
            'Statutory Provision (USD)'
        ])
        for t in prov['tiers']:
            writer.writerow([
                t['name_en'],
                t['name_km'],
                t['dpd_range'],
                t['loan_count'],
                f"{t['total_balance']:.2f}",
                f"{t['rate_pct']:.1f}%",
                f"{t['required_provision']:.2f}"
            ])
        writer.writerow([
            'TOTAL PORTFOLIO',
            'ផលប័ត្រសរុប',
            '-',
            prov['total_loans'],
            f"{prov['total_portfolio']:.2f}",
            '-',
            f"{prov['total_provision']:.2f}"
        ])

    elif report_type == 'delinquency':
        prov = calculate_nbc_provisioning()
        writer.writerow(['PORTFOLIO-AT-RISK (PAR 30 / PAR 90) DELINQUENCY REPORT'])
        writer.writerow(['Generated At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        writer.writerow([
            'Application No',
            'Borrower Name',
            'Loan Product',
            'Currency',
            'Outstanding Principal',
            'Days Past Due (DPD)',
            'NBC Classification Tier',
        ])
        for row in prov['loan_details']:
            writer.writerow([
                row['application_no'],
                row['borrower_name'],
                row['product_name'],
                row['currency'],
                f"{row['outstanding']:.2f}",
                row['dpd'],
                row['tier_name']
            ])

    elif report_type == 'repayments':
        receipts = PaymentReceipt.objects.select_related('installment', 'loan', 'payer', 'verified_by').order_by('-created_at')
        writer.writerow(['BAKONG KHQR & CASH REPAYMENT RECONCILIATION AUDIT LEDGER'])
        writer.writerow(['Generated At', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        writer.writerow([
            'Transaction Ref',
            'Created Date',
            'Borrower Name',
            'Loan No',
            'Installment #',
            'Amount',
            'Currency',
            'Payment Method',
            'Reconciliation Status',
            'Verified By',
            'Verified At',
            'Officer Notes',
        ])
        for r in receipts:
            writer.writerow([
                r.transaction_reference,
                r.created_at.strftime('%Y-%m-%d %H:%M'),
                r.payer.get_full_name() or r.payer.username,
                r.loan.application_no,
                r.installment.sequence_number,
                f"{r.amount:.2f}",
                r.currency,
                r.get_payment_method_display(),
                r.get_status_display(),
                r.verified_by.get_full_name() or r.verified_by.username if r.verified_by else 'System / N/A',
                r.verified_at.strftime('%Y-%m-%d %H:%M') if r.verified_at else '-',
                r.officer_notes or '',
            ])

    return buffer.getvalue()
