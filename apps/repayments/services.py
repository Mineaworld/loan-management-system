import datetime
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.loans.models import LoanApplication, ActionLog
from apps.repayments.models import LoanInstallment, PaymentReceipt


def _add_months(source_date, months):
    """Accurately increments date by N calendar months, clamping day to end of month."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    days_in_month = [31, 29 if is_leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    day = min(source_date.day, days_in_month)
    return datetime.date(year, month, day)


def generate_amortization_schedule(application, start_date=None):
    """
    Generates exact NBC Reducing Balance amortization schedule.
    Enforces strict zero-balance reconciliation: final period n absorbs rounding differences
    so remaining_balance reconciles to strictly Decimal('0.00') or Decimal('0').
    """
    if start_date is None:
        start_date = timezone.now().date()

    n = int(getattr(application, 'tenure_months', 0) or 0)
    principal = getattr(application, 'amount', None)
    product = getattr(application, 'product', None)
    if n <= 0 or not principal or not product or Decimal(str(principal)) <= Decimal('0.00'):
        return []

    principal_amount = Decimal(str(principal))
    annual_rate = Decimal(str(product.interest_rate))
    monthly_rate = annual_rate / Decimal('1200')
    currency = getattr(application, 'currency', 'USD')
    round_factor = Decimal('1') if currency == 'KHR' else Decimal('0.01')
    zero_val = Decimal('0') if currency == 'KHR' else Decimal('0.00')

    emi = application.emi
    balance = principal_amount
    schedule = []

    for t in range(1, n + 1):
        due_date = _add_months(start_date, t)
        interest = (balance * monthly_rate).quantize(round_factor, rounding=ROUND_HALF_UP)

        if t < n:
            principal_comp = emi - interest
            balance = balance - principal_comp
            total_emi = emi
        else:
            principal_comp = balance
            total_emi = principal_comp + interest
            balance = zero_val

        schedule.append({
            'sequence_number': t,
            'due_date': due_date,
            'total_installment_emi': total_emi,
            'principal_component': principal_comp,
            'interest_component': interest,
            'remaining_balance': balance,
        })

    return schedule


@transaction.atomic
def execute_disbursal(application, officer=None, notes=None):
    """
    Executes loan disbursal in an atomic transaction:
    - Row-level database lock (select_for_update) to prevent race conditions
    - Verifies status is eligible for disbursal (strictly APPROVED)
    - Sets status = ACTIVE, disbursed_at = now
    - Creates audit ActionLog record
    - Generates and bulk-creates persistent LoanInstallment records
    """
    if not getattr(application, 'id', None):
        raise ValidationError("Application must be saved to database before disbursal.")

    app_locked = LoanApplication.objects.select_for_update().get(id=application.id)
    if app_locked.status != LoanApplication.Status.APPROVED:
        raise ValidationError(
            f"Cannot disburse application in status '{app_locked.get_status_display()}'. Status must be APPROVED."
        )

    old_status = app_locked.status
    now = timezone.now()

    app_locked.status = LoanApplication.Status.ACTIVE
    app_locked.disbursed_at = now
    if officer:
        app_locked.assigned_officer = officer
    app_locked.save()

    ActionLog.objects.create(
        loan=app_locked,
        changed_by=officer,
        from_status=old_status,
        to_status=LoanApplication.Status.ACTIVE,
        action_notes=notes or 'Loan disbursed and repayment schedule activated.'
    )

    app_locked.installments.all().delete()

    schedule = generate_amortization_schedule(app_locked, start_date=now.date())
    installments = [
        LoanInstallment(
            loan=app_locked,
            sequence_number=item['sequence_number'],
            due_date=item['due_date'],
            total_installment_emi=item['total_installment_emi'],
            principal_component=item['principal_component'],
            interest_component=item['interest_component'],
            remaining_balance=item['remaining_balance'],
            status=LoanInstallment.Status.PENDING,
        )
        for item in schedule
    ]

    created = LoanInstallment.objects.bulk_create(installments)
    application.refresh_from_db()
    return created


@transaction.atomic
def record_repayment(installment, payment_method, payer, reference=None, notes=None):
    """
    Atomically records an installment payment:
    - Row-level lock on installment and loan
    - Transitions installment status to PAID with timestamp
    - Generates/updates verified PaymentReceipt
    - Transitions loan to COMPLETED if all installments are settled
    - Logs audit trail ActionLog
    """
    if not getattr(installment, 'id', None):
        raise ValidationError("Installment must be saved in database before recording repayment.")

    inst_locked = LoanInstallment.objects.select_for_update().select_related('loan').get(id=installment.id)
    if inst_locked.status == LoanInstallment.Status.PAID:
        raise ValidationError(f"Installment #{inst_locked.sequence_number} is already paid.")

    loan_locked = LoanApplication.objects.select_for_update().get(id=inst_locked.loan_id)
    now = timezone.now()

    inst_locked.status = LoanInstallment.Status.PAID
    inst_locked.paid_at = now
    inst_locked.save()

    txn_ref = reference or f"TXN-KHQR-{now:%y%m%d%H%M%S}-{inst_locked.sequence_number:02d}"

    receipt, _ = PaymentReceipt.objects.update_or_create(
        installment=inst_locked,
        defaults={
            'loan': loan_locked,
            'payer': payer,
            'transaction_reference': txn_ref,
            'amount': inst_locked.total_installment_emi,
            'currency': loan_locked.currency,
            'payment_method': payment_method,
            'status': PaymentReceipt.Status.VERIFIED,
            'verified_by': payer if getattr(payer, 'is_staff', False) or getattr(payer, 'role', '') in ['OFFICER', 'ADMIN'] else None,
            'verified_at': now,
            'officer_notes': notes or 'Instant settlement via Bakong KHQR.',
        }
    )

    unpaid_count = loan_locked.installments.exclude(status=LoanInstallment.Status.PAID).count()
    if unpaid_count == 0:
        loan_locked.status = LoanApplication.Status.COMPLETED
        loan_locked.save()
        ActionLog.objects.create(
            loan=loan_locked,
            changed_by=payer,
            from_status=LoanApplication.Status.ACTIVE,
            to_status=LoanApplication.Status.COMPLETED,
            action_notes="All scheduled installments fully repaid. Loan facility closed."
        )
    else:
        ActionLog.objects.create(
            loan=loan_locked,
            changed_by=payer,
            from_status=loan_locked.status,
            to_status=loan_locked.status,
            action_notes=f"Installment #{inst_locked.sequence_number} (${inst_locked.total_installment_emi}) settled via {payment_method}."
        )

    installment.refresh_from_db()
    return inst_locked, receipt


@transaction.atomic
def process_slip_upload(installment, payer, slip_file, transaction_ref=None, notes=None):
    """
    Submits a transfer slip for officer verification:
    - Sets installment to VERIFYING
    - Creates pending PaymentReceipt
    - Logs audit trail ActionLog
    """
    inst_locked = LoanInstallment.objects.select_for_update().select_related('loan').get(id=installment.id)
    if inst_locked.status == LoanInstallment.Status.PAID:
        raise ValidationError(f"Installment #{inst_locked.sequence_number} is already paid.")

    now = timezone.now()
    inst_locked.status = LoanInstallment.Status.VERIFYING
    inst_locked.save()

    txn_ref = transaction_ref or f"TXN-SLIP-{now:%y%m%d%H%M%S}-{inst_locked.sequence_number:02d}"

    receipt = PaymentReceipt.objects.create(
        installment=inst_locked,
        loan=inst_locked.loan,
        payer=payer,
        transaction_reference=txn_ref,
        amount=inst_locked.total_installment_emi,
        currency=inst_locked.loan.currency,
        payment_method=PaymentReceipt.PaymentMethod.BAKONG_KHQR,
        slip_image=slip_file,
        status=PaymentReceipt.Status.PENDING,
        officer_notes=notes or 'Borrower uploaded transfer slip for reconciliation.'
    )

    ActionLog.objects.create(
        loan=inst_locked.loan,
        changed_by=payer,
        from_status=inst_locked.loan.status,
        to_status=inst_locked.loan.status,
        action_notes=f"Payment slip submitted for installment #{inst_locked.sequence_number} (Ref: {txn_ref})."
    )

    installment.refresh_from_db()
    return receipt


@transaction.atomic
def verify_repayment_receipt(receipt, officer, approved=True, notes=None):
    """
    Processes an officer decision on a pending PaymentReceipt:
    - If approved: marks VERIFIED, sets installment to PAID, decrements debt
    - If rejected: marks REJECTED, reverts installment to PENDING or OVERDUE
    """
    rec_locked = PaymentReceipt.objects.select_for_update().select_related('installment', 'loan').get(id=receipt.id)
    if rec_locked.status != PaymentReceipt.Status.PENDING:
        raise ValidationError(f"Receipt {rec_locked.transaction_reference} has already been processed.")

    now = timezone.now()
    rec_locked.verified_by = officer
    rec_locked.verified_at = now
    rec_locked.officer_notes = notes or ('Verified by officer.' if approved else 'Rejected by officer.')

    inst_locked = LoanInstallment.objects.select_for_update().get(id=rec_locked.installment_id)
    loan_locked = LoanApplication.objects.select_for_update().get(id=rec_locked.loan_id)

    if approved:
        rec_locked.status = PaymentReceipt.Status.VERIFIED
        rec_locked.save()

        inst_locked.status = LoanInstallment.Status.PAID
        inst_locked.paid_at = now
        inst_locked.save()

        unpaid_count = loan_locked.installments.exclude(status=LoanInstallment.Status.PAID).count()
        if unpaid_count == 0:
            loan_locked.status = LoanApplication.Status.COMPLETED
            loan_locked.save()
            ActionLog.objects.create(
                loan=loan_locked,
                changed_by=officer,
                from_status=LoanApplication.Status.ACTIVE,
                to_status=LoanApplication.Status.COMPLETED,
                action_notes="All scheduled installments fully repaid. Loan facility closed."
            )
        else:
            ActionLog.objects.create(
                loan=loan_locked,
                changed_by=officer,
                from_status=loan_locked.status,
                to_status=loan_locked.status,
                action_notes=f"Receipt {rec_locked.transaction_reference} verified. Installment #{inst_locked.sequence_number} marked PAID."
            )
    else:
        rec_locked.status = PaymentReceipt.Status.REJECTED
        rec_locked.save()

        if inst_locked.due_date < now.date():
            inst_locked.status = LoanInstallment.Status.OVERDUE
        else:
            inst_locked.status = LoanInstallment.Status.PENDING
        inst_locked.save()

        ActionLog.objects.create(
            loan=loan_locked,
            changed_by=officer,
            from_status=loan_locked.status,
            to_status=loan_locked.status,
            action_notes=f"Receipt {rec_locked.transaction_reference} rejected: {notes or 'Invalid transfer slip'}."
        )

    receipt.refresh_from_db()
    return rec_locked
