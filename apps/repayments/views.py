from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.views import borrower_required, officer_required
from apps.loans.models import LoanApplication
from apps.repayments.models import LoanInstallment, PaymentReceipt
from apps.repayments.services import (
    execute_disbursal,
    record_repayment,
    process_slip_upload,
    verify_repayment_receipt
)


@login_required
@officer_required
@require_POST
def disburse_loan_api(request, pk):
    """POST API to disburse an approved loan and activate its persistent installment schedule."""
    application = get_object_or_404(LoanApplication, pk=pk)
    remarks = request.POST.get('remarks', '').strip()
    try:
        execute_disbursal(application, request.user, notes=remarks or None)
        return JsonResponse({
            'success': True,
            'application_no': application.application_no,
            'status': application.status,
            'status_display': application.get_status_display(),
            'message': f"Loan {application.application_no} disbursed successfully."
        })
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@borrower_required
@require_POST
def simulate_instant_pay_api(request):
    """Simulates 1-click instant payment settlement via National Bank of Cambodia Bakong KHQR."""
    installment_id = request.POST.get('installment_id')
    if not installment_id:
        return JsonResponse({'success': False, 'error': 'Missing installment_id.'}, status=400)

    installment = get_object_or_404(
        LoanInstallment.objects.select_related('loan'),
        id=installment_id,
        loan__borrower=request.user
    )

    try:
        updated_inst, receipt = record_repayment(
            installment=installment,
            payment_method=PaymentReceipt.PaymentMethod.BAKONG_KHQR,
            payer=request.user
        )
        return JsonResponse({
            'success': True,
            'message': f"Installment #{updated_inst.sequence_number} successfully settled via Bakong KHQR.",
            'installment_id': updated_inst.id,
            'sequence_number': updated_inst.sequence_number,
            'status': updated_inst.status,
            'status_display': updated_inst.get_status_display(),
            'paid_at': updated_inst.paid_at.strftime('%Y-%m-%d %H:%M:%S'),
            'transaction_reference': receipt.transaction_reference,
            'loan_status': updated_inst.loan.status,
            'loan_status_display': updated_inst.loan.get_status_display(),
        })
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@borrower_required
@require_POST
def upload_payment_slip_view(request):
    """Handles borrower file upload of bank transfer payment slips."""
    installment_id = request.POST.get('installment_id')
    slip_image = request.FILES.get('slip_image')
    notes = request.POST.get('notes', '').strip()
    txn_ref = request.POST.get('transaction_reference', '').strip()

    if not installment_id:
        messages.error(request, "សូមជ្រើសរើសដំណាក់កាលបង់ប្រាក់ / Please select an installment.")
        return redirect('borrower')

    installment = get_object_or_404(
        LoanInstallment.objects.select_related('loan'),
        id=installment_id,
        loan__borrower=request.user
    )

    try:
        receipt = process_slip_upload(
            installment=installment,
            payer=request.user,
            slip_file=slip_image,
            transaction_ref=txn_ref or None,
            notes=notes or None
        )
        messages.success(
            request,
            f"បង្កាន់ដៃផ្ទេរប្រាក់ {receipt.transaction_reference} ត្រូវបានបញ្ជូនដោយជោគជ័យ! រង់ចាំការផ្ទៀងផ្ទាត់ពីមន្ត្រីឥណទាន។"
        )
    except ValidationError as e:
        messages.error(request, str(e))

    return redirect(f"{reverse('borrower')}?tab=history")


@login_required
@officer_required
@require_POST
def verify_receipt_api(request, pk):
    """Processes officer approval of a pending bank transfer slip."""
    receipt = get_object_or_404(PaymentReceipt, pk=pk)
    notes = request.POST.get('notes', '').strip()

    try:
        verify_repayment_receipt(receipt, request.user, approved=True, notes=notes or None)
        return JsonResponse({
            'success': True,
            'message': f"Receipt {receipt.transaction_reference} verified. Installment settled.",
            'receipt_id': receipt.id,
            'status': receipt.status,
            'status_display': receipt.get_status_display()
        })
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@officer_required
@require_POST
def reject_receipt_api(request, pk):
    """Processes officer rejection of an invalid bank transfer slip."""
    receipt = get_object_or_404(PaymentReceipt, pk=pk)
    notes = request.POST.get('notes', '').strip()

    try:
        verify_repayment_receipt(receipt, request.user, approved=False, notes=notes or None)
        return JsonResponse({
            'success': True,
            'message': f"Receipt {receipt.transaction_reference} rejected.",
            'receipt_id': receipt.id,
            'status': receipt.status,
            'status_display': receipt.get_status_display()
        })
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
