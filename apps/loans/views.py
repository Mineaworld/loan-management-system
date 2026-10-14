import json
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from apps.accounts.models import User, Branch
from apps.accounts.views import borrower_required, officer_required
from .forms import LoanApplicationForm
from .models import LoanApplication, LoanProduct, ActionLog, LoanInstallment, PaymentReceipt
from .services import (
    calculate_cbc_score,
    execute_disbursal,
    calculate_nbc_provisioning,
    calculate_delinquency_metrics,
    verify_repayment_receipt,
)
from apps.repayments.views import (
    disburse_loan_api,
    simulate_instant_pay_api,
    upload_payment_slip_view,
    verify_receipt_api,
    reject_receipt_api,
)
from apps.reports.views import (
    nbc_provisioning_api,
    export_report_csv_view,
)


@login_required
@borrower_required
def borrower_portal_view(request):
    products = LoanProduct.objects.filter(is_active=True).order_by('name')
    user_applications = LoanApplication.objects.filter(borrower=request.user).select_related(
        'product', 'branch', 'assigned_officer', 'assigned_officer__officer_profile', 'assigned_officer__officer_profile__branch'
    ).order_by('-created_at')

    active_disbursed_loan = user_applications.filter(status__in=[
        LoanApplication.Status.ACTIVE,
        LoanApplication.Status.DISBURSED
    ]).first()

    approved_pending_loan = user_applications.filter(status=LoanApplication.Status.APPROVED).first()
    approved_loan = active_disbursed_loan or approved_pending_loan

    pending_application = user_applications.filter(status__in=[
        LoanApplication.Status.SUBMITTED,
        LoanApplication.Status.UNDER_REVIEW
    ]).first()
    active_application = approved_loan or pending_application or user_applications.first()

    servicing_officer = getattr(active_application, 'assigned_officer', None) if active_application else None
    if not servicing_officer:
        user_branch = getattr(getattr(request.user, 'borrower_profile', None), 'servicing_branch', None)
        if user_branch:
            servicing_officer = User.objects.filter(
                role=User.Role.OFFICER,
                officer_profile__branch=user_branch
            ).select_related('officer_profile', 'officer_profile__branch').first()

    servicing_branch = None
    if active_application and active_application.branch:
        servicing_branch = active_application.branch
    elif servicing_officer and hasattr(servicing_officer, 'officer_profile') and servicing_officer.officer_profile.branch:
        servicing_branch = servicing_officer.officer_profile.branch
    elif hasattr(request.user, 'borrower_profile') and request.user.borrower_profile.servicing_branch:
        servicing_branch = request.user.borrower_profile.servicing_branch
    else:
        servicing_branch = Branch.objects.filter(code='HO-PP').first()

    installments = []
    next_installment = None
    days_remaining = 0
    paid_count = 0
    total_count = 0
    progress_pct = 0
    remaining_principal = Decimal('0.00')

    if active_disbursed_loan:
        installments = list(active_disbursed_loan.installments.all().order_by('sequence_number'))
        total_count = len(installments)
        unpaid_insts = [inst for inst in installments if inst.status != LoanInstallment.Status.PAID]
        paid_insts = [inst for inst in installments if inst.status == LoanInstallment.Status.PAID]
        paid_count = len(paid_insts)
        progress_pct = int((paid_count / total_count * 100)) if total_count > 0 else 0

        if unpaid_insts:
            next_installment = unpaid_insts[0]
            days_remaining = (next_installment.due_date - timezone.now().date()).days
            remaining_principal = sum((inst.principal_component for inst in unpaid_insts), Decimal('0.00'))
        else:
            remaining_principal = Decimal('0.00')
    elif approved_pending_loan:
        remaining_principal = approved_pending_loan.amount

    active_section = 'sec-my-loan'
    req_tab = request.GET.get('tab')
    if req_tab in ['my-loan', 'applications', 'schedule', 'pay', 'apply', 'history']:
        active_section = f'sec-{req_tab}'

    if request.method == 'POST':
        form = LoanApplicationForm(request.POST)
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

        if form.is_valid():
            application = form.save(borrower=request.user)
            success_msg = (
                f"ពាក្យស្នើសុំលេខ {application.application_no} ត្រូវបានបញ្ជូនដោយជោគជ័យ! / "
                f"Application {application.application_no} submitted successfully."
            )
            messages.success(request, success_msg)
            redirect_target = request.path if request.path else reverse('loans:borrower_portal')
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'message': success_msg,
                    'redirect_url': redirect_target
                })
            return redirect(redirect_target)
        else:
            active_section = 'sec-apply'
            error_list = []
            for field, errors in form.errors.items():
                for err in errors:
                    error_list.append(str(err))
                    messages.error(request, f"{err}")
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'errors': error_list,
                    'field_errors': {f: [str(e) for e in errs] for f, errs in form.errors.items()}
                }, status=400)
    else:
        form = LoanApplicationForm()

    user_receipts = PaymentReceipt.objects.filter(
        Q(payer=request.user) | Q(loan__borrower=request.user)
    ).distinct().select_related('installment', 'loan').order_by('-created_at')[:20]

    return render(request, 'loans/borrower_dashboard.html', {
        'form': form,
        'products': products,
        'branches': Branch.objects.all().order_by('code'),
        'servicing_officer': servicing_officer,
        'servicing_branch': servicing_branch,
        'user_applications': user_applications,
        'active_application': active_application,
        'approved_loan': approved_loan,
        'approved_pending_loan': approved_pending_loan,
        'active_disbursed_loan': active_disbursed_loan,
        'pending_application': pending_application,
        'installments': installments,
        'next_installment': next_installment,
        'days_remaining': days_remaining,
        'paid_count': paid_count,
        'total_count': total_count,
        'progress_pct': progress_pct,
        'remaining_principal': remaining_principal,
        'user_receipts': user_receipts,
        'active_section': active_section,
    })


@login_required
@officer_required
def officer_dashboard_view(request):
    if request.method == 'POST':
        app_id = request.POST.get('application_id')
        action = request.POST.get('action')
        remarks = request.POST.get('remarks', '').strip()

        if app_id and action:
            application = get_object_or_404(LoanApplication, id=app_id)
            old_status = application.status

            if action == 'APPROVE':
                with transaction.atomic():
                    application.status = LoanApplication.Status.APPROVED
                    application.assigned_officer = request.user
                    application.approved_at = timezone.now()
                    application.officer_remarks = remarks or 'Approved by credit officer.'
                    application.save()
                    ActionLog.objects.create(
                        loan=application,
                        changed_by=request.user,
                        from_status=old_status,
                        to_status=LoanApplication.Status.APPROVED,
                        action_notes=remarks or 'Approved by credit officer.'
                    )
                messages.success(request, f"ពាក្យស្នើសុំ {application.application_no} ត្រូវបានអនុម័ត! / Application {application.application_no} approved.")

            elif action == 'REJECT':
                with transaction.atomic():
                    application.status = LoanApplication.Status.REJECTED
                    application.assigned_officer = request.user
                    application.officer_remarks = remarks or 'Rejected by credit committee.'
                    application.save()
                    ActionLog.objects.create(
                        loan=application,
                        changed_by=request.user,
                        from_status=old_status,
                        to_status=LoanApplication.Status.REJECTED,
                        action_notes=remarks or 'Rejected by credit committee.'
                    )
                messages.info(request, f"ពាក្យស្នើសុំ {application.application_no} ត្រូវបានបដិសេធ / Application {application.application_no} rejected.")

            elif action == 'REVIEW':
                with transaction.atomic():
                    application.status = LoanApplication.Status.UNDER_REVIEW
                    application.assigned_officer = request.user
                    if remarks:
                        application.officer_remarks = remarks
                    application.save()
                    ActionLog.objects.create(
                        loan=application,
                        changed_by=request.user,
                        from_status=old_status,
                        to_status=LoanApplication.Status.UNDER_REVIEW,
                        action_notes=remarks or 'Marked under review.'
                    )
                messages.info(request, f"ពាក្យស្នើសុំ {application.application_no} បានប្តូរទៅស្ថានភាពកំពុងពិនិត្យ / Marked under review.")

            elif action == 'CLAIM':
                with transaction.atomic():
                    application.assigned_officer = request.user
                    application.status = LoanApplication.Status.UNDER_REVIEW
                    application.save()
                    ActionLog.objects.create(
                        loan=application,
                        changed_by=request.user,
                        from_status=old_status,
                        to_status=LoanApplication.Status.UNDER_REVIEW,
                        action_notes=remarks or f"ពាក្យស្នើសុំត្រូវបានទទួលបន្ទុកដោយមន្ត្រី {request.user.get_full_name() or request.user.username} / Claimed by Credit Officer."
                    )
                messages.success(request, f"អ្នកបានទទួលបន្ទុកពាក្យស្នើសុំ {application.application_no} រួចរាល់! / You claimed application {application.application_no}.")

            elif action == 'REASSIGN':
                target_officer_id = request.POST.get('target_officer_id')
                if target_officer_id:
                    target_officer = get_object_or_404(User, id=target_officer_id, role__in=[User.Role.OFFICER, User.Role.ADMIN])
                    with transaction.atomic():
                        application.assigned_officer = target_officer
                        application.save()
                        ActionLog.objects.create(
                            loan=application,
                            changed_by=request.user,
                            from_status=old_status,
                            to_status=application.status,
                            action_notes=remarks or f"Reassigned to Credit Officer {target_officer.get_full_name() or target_officer.username}."
                        )
                    messages.success(request, f"ពាក្យស្នើសុំ {application.application_no} ត្រូវបានចាត់តាំងទៅកាន់ {target_officer.get_full_name() or target_officer.username} / Reassigned successfully.")

            elif action == 'DISBURSE':
                try:
                    execute_disbursal(application, request.user, notes=remarks or None)
                    messages.success(
                        request,
                        f"ឥណទាន {application.application_no} ត្រូវបានបើកផ្តល់ និងបង្កើតតារាងបង់រំលស់ជោគជ័យ! / Loan {application.application_no} disbursed."
                    )
                except ValidationError as e:
                    messages.error(request, str(e))

            tab = request.POST.get('tab') or request.GET.get('tab')
            scope = request.POST.get('scope') or request.GET.get('scope')
            query_params = []
            if tab:
                query_params.append(f"tab={tab}")
            if scope and scope != 'all':
                query_params.append(f"scope={scope}")
            status_param = request.POST.get('status') or request.GET.get('status')
            if status_param and status_param != 'ALL':
                query_params.append(f"status={status_param}")
            branch_param = request.POST.get('branch') or request.GET.get('branch')
            if branch_param and branch_param != 'ALL':
                query_params.append(f"branch={branch_param}")
            if query_params:
                return redirect(f"{reverse('loans:officer_dashboard')}?{'&'.join(query_params)}")
            return redirect('loans:officer_dashboard')

        receipt_id = request.POST.get('receipt_id')
        if receipt_id and action in ['VERIFY_RECEIPT', 'REJECT_RECEIPT']:
            receipt = get_object_or_404(PaymentReceipt, id=receipt_id)
            if action == 'VERIFY_RECEIPT':
                try:
                    verify_repayment_receipt(receipt, request.user, approved=True, notes=remarks or None)
                    messages.success(
                        request,
                        f"វិក្កយបត្រ {receipt.transaction_reference} ត្រូវបានផ្ទៀងផ្ទាត់ និងកត់ត្រាការទូទាត់រួចរាល់! / Receipt {receipt.transaction_reference} verified."
                    )
                except ValidationError as e:
                    messages.error(request, str(e))
            elif action == 'REJECT_RECEIPT':
                try:
                    verify_repayment_receipt(receipt, request.user, approved=False, notes=remarks or None)
                    messages.warning(
                        request,
                        f"វិក្កយបត្រ {receipt.transaction_reference} ត្រូវបានបដិសេធ / Receipt {receipt.transaction_reference} rejected."
                    )
                except ValidationError as e:
                    messages.error(request, str(e))
            tab = request.POST.get('tab') or request.GET.get('tab')
            if tab:
                return redirect(f"{reverse('loans:officer_dashboard')}?tab={tab}")
            return redirect('loans:officer_dashboard')

    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'ALL').strip().upper()
    scope = request.GET.get('scope', 'all').strip().lower()
    branch_filter = request.GET.get('branch', 'ALL').strip().upper()

    base_applications = LoanApplication.objects.select_related(
        'borrower', 'product', 'borrower__borrower_profile', 'branch', 'assigned_officer', 'assigned_officer__officer_profile'
    ).prefetch_related('collaterals', 'action_logs').all()

    if branch_filter and branch_filter != 'ALL':
        base_applications = base_applications.filter(branch__code=branch_filter)

    my_queue_count = base_applications.filter(assigned_officer=request.user).count()
    unassigned_count = base_applications.filter(assigned_officer__isnull=True).count()
    all_queue_count = base_applications.count()

    applications = base_applications

    if scope == 'my_queue':
        applications = applications.filter(assigned_officer=request.user)
    elif scope == 'unassigned':
        applications = applications.filter(assigned_officer__isnull=True)
    # else 'all' retains all branch applications

    if query:
        applications = applications.filter(
            Q(application_no__icontains=query) |
            Q(borrower__first_name__icontains=query) |
            Q(borrower__last_name__icontains=query) |
            Q(borrower__username__icontains=query) |
            Q(borrower__phone_number__icontains=query)
        )

    if status_filter and status_filter != 'ALL':
        applications = applications.filter(status=status_filter)

    total_count = LoanApplication.objects.count()
    pending_count = LoanApplication.objects.filter(status__in=[
        LoanApplication.Status.SUBMITTED,
        LoanApplication.Status.UNDER_REVIEW
    ]).count()
    approved_count = LoanApplication.objects.filter(status__in=[
        LoanApplication.Status.APPROVED,
        LoanApplication.Status.DISBURSED,
        LoanApplication.Status.ACTIVE
    ]).count()
    total_disbursed = LoanApplication.objects.filter(status__in=[
        LoanApplication.Status.APPROVED,
        LoanApplication.Status.DISBURSED,
        LoanApplication.Status.ACTIVE
    ]).aggregate(total=Sum('amount'))['total'] or 0

    recent_applications = applications.filter(
        status__in=[LoanApplication.Status.SUBMITTED, LoanApplication.Status.UNDER_REVIEW]
    )[:5]

    first_app = recent_applications.first() or applications.first()

    active_loans = LoanApplication.objects.filter(status__in=[
        LoanApplication.Status.APPROVED,
        LoanApplication.Status.DISBURSED,
        LoanApplication.Status.ACTIVE
    ]).select_related('borrower', 'product', 'borrower__borrower_profile', 'branch', 'assigned_officer').prefetch_related('installments').order_by('-created_at')

    receipts = PaymentReceipt.objects.select_related(
        'installment', 'loan', 'payer', 'verified_by'
    ).order_by('-created_at')
    pending_receipts_count = receipts.filter(status=PaymentReceipt.Status.PENDING).count()

    nbc_data = calculate_nbc_provisioning()
    delinquency_data = calculate_delinquency_metrics()

    staff_users = []
    total_staff_count = 0
    officer_count = 0
    admin_count = 0
    borrower_count = 0
    if request.user.is_admin_user:
        staff_users = User.objects.select_related('officer_profile', 'borrower_profile').order_by('-date_joined')
        total_staff_count = staff_users.filter(role__in=[User.Role.OFFICER, User.Role.ADMIN]).count()
        officer_count = staff_users.filter(role=User.Role.OFFICER).count()
        admin_count = staff_users.filter(role=User.Role.ADMIN).count()
        borrower_count = staff_users.filter(role=User.Role.BORROWER).count()

    active_section = 'sec-overview'
    req_tab = request.GET.get('tab')
    if req_tab in ['overview', 'applications', 'loans', 'repayments', 'reports', 'staff']:
        active_section = f'sec-{req_tab}'
    elif request.GET.get('scope') or (status_filter and status_filter != 'ALL') or (branch_filter and branch_filter != 'ALL') or query:
        active_section = 'sec-applications'

    product_stats = list(LoanApplication.objects.values('product__name').annotate(
        count=Count('id'),
        total_amt=Sum('amount')
    ).order_by('-count'))
    chart_product_labels = [p['product__name'] for p in product_stats] if product_stats else ['SME Business Loan', 'Personal Loan', 'Agriculture Loan']
    chart_product_counts = [p['count'] for p in product_stats] if product_stats else [1, 1, 1]
    chart_labels_json = json.dumps(chart_product_labels)
    chart_counts_json = json.dumps(chart_product_counts)

    return render(request, 'loans/officer_dashboard.html', {
        'active_section': active_section,
        'chart_labels_json': chart_labels_json,
        'chart_counts_json': chart_counts_json,
        'applications': applications,
        'recent_applications': recent_applications,
        'first_app': first_app,
        'active_loans': active_loans,
        'receipts': receipts,
        'pending_receipts_count': pending_receipts_count,
        'nbc_data': nbc_data,
        'delinquency_data': delinquency_data,
        'search_query': query,
        'selected_status': status_filter,
        'current_scope': scope,
        'selected_branch': branch_filter,
        'my_queue_count': my_queue_count,
        'unassigned_count': unassigned_count,
        'all_queue_count': all_queue_count,
        'branches': Branch.objects.all().order_by('code'),
        'all_officers': User.objects.filter(role__in=[User.Role.OFFICER, User.Role.ADMIN]).select_related('officer_profile'),
        'total_count': total_count,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'total_disbursed': total_disbursed,
        'staff_users': staff_users,
        'total_staff_count': total_staff_count,
        'officer_count': officer_count,
        'admin_count': admin_count,
        'borrower_count': borrower_count,
    })


@login_required
@officer_required
def application_cbc_api(request, pk):
    """
    API endpoint returning simulated CBC credit scoring, DTI, collateral valuation,
    risk grade, recommendation, and audit action logs for an application.
    """
    application = get_object_or_404(
        LoanApplication.objects.select_related(
            'borrower', 'product', 'borrower__borrower_profile', 'branch', 'assigned_officer'
        ).prefetch_related('collaterals', 'action_logs'),
        pk=pk
    )
    cbc_data = calculate_cbc_score(application)

    collaterals_list = [
        {
            'type': c.collateral_type,
            'title_deed': c.title_deed_number or 'N/A',
            'valuation': float(c.estimated_valuation),
            'description': c.description or '',
        }
        for c in application.collaterals.all()
    ]

    logs_list = [
        {
            'changed_by': log.changed_by.get_full_name() or log.changed_by.username if log.changed_by else 'System',
            'from_status': log.from_status,
            'to_status': log.to_status,
            'action_notes': log.action_notes or '',
            'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M'),
        }
        for log in application.action_logs.all()
    ]

    return JsonResponse({
        'success': True,
        'application_no': application.application_no,
        'borrower_name': application.borrower.get_full_name() or application.borrower.username,
        'branch_code': application.branch.code if application.branch else 'HO-PP',
        'branch_name': application.branch.name_km if application.branch else 'ការិយាល័យកណ្តាល (ភ្នំពេញ)',
        'branch_name_en': application.branch.name_en if application.branch else 'Head Office - Phnom Penh',
        'assigned_officer': application.assigned_officer.get_full_name() or application.assigned_officer.username if application.assigned_officer else None,
        'amount': float(application.amount),
        'currency': application.currency,
        'tenure_months': application.tenure_months,
        'emi': float(application.emi),
        'monthly_income': float(application.monthly_income),
        'purpose': application.purpose,
        'status': application.status,
        'status_display': application.get_status_display(),
        'cbc_score': cbc_data['cbc_score'],
        'risk_grade': cbc_data['risk_grade'],
        'dti': float(cbc_data['dti']),
        'collateral_coverage': float(cbc_data['collateral_coverage']),
        'total_collateral': float(cbc_data['total_collateral']),
        'recommendation': cbc_data['recommendation'],
        'recommendation_en': cbc_data['recommendation_en'],
        'collaterals': collaterals_list,
        'action_logs': logs_list,
    })




@login_required
@officer_required
@require_POST
def update_application_status_api(request, pk):
    application = get_object_or_404(LoanApplication, pk=pk)
    new_status = request.POST.get('status')
    remarks = request.POST.get('remarks', '').strip()

    if new_status in [LoanApplication.Status.ACTIVE, LoanApplication.Status.DISBURSED]:
        try:
            execute_disbursal(application, request.user, notes=remarks or None)
            return JsonResponse({
                'success': True,
                'new_status': application.status,
                'status_display': application.get_status_display(),
                'message': f"Loan {application.application_no} disbursed and activated."
            })
        except ValidationError as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    if new_status in dict(LoanApplication.Status.choices):
        old_status = application.status
        with transaction.atomic():
            application.status = new_status
            application.assigned_officer = request.user
            if remarks:
                application.officer_remarks = remarks
            if new_status == LoanApplication.Status.APPROVED:
                application.approved_at = timezone.now()
            application.save()

            ActionLog.objects.create(
                loan=application,
                changed_by=request.user,
                from_status=old_status,
                to_status=new_status,
                action_notes=remarks or f"Status updated to {new_status} via API."
            )

        return JsonResponse({
            'success': True,
            'new_status': application.status,
            'status_display': application.get_status_display()
        })
    return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)



__all__ = [
    'borrower_portal_view',
    'officer_dashboard_view',
    'application_cbc_api',
    'update_application_status_api',
    'disburse_loan_api',
    'simulate_instant_pay_api',
    'upload_payment_slip_view',
    'verify_receipt_api',
    'reject_receipt_api',
    'nbc_provisioning_api',
    'export_report_csv_view',
]

