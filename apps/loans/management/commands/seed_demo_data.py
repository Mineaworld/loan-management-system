import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import User, BorrowerProfile, OfficerProfile
from apps.loans.models import LoanProduct, LoanApplication, Collateral, ActionLog, LoanInstallment, PaymentReceipt
from apps.loans.services import execute_disbursal


class Command(BaseCommand):
    help = 'Seed demo users, loan products, sample applications, collaterals, and active installments'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'System',
                'last_name': 'Admin',
                'email': 'admin@lms.com.kh',
                'role': User.Role.ADMIN,
                'is_staff': True,
                'is_superuser': True,
            }
        )
        admin_user.set_password('pass123')
        admin_user.save()

        officer_user, _ = User.objects.get_or_create(
            username='officer1',
            defaults={
                'first_name': 'សុខា',
                'last_name': 'ឆាយ',
                'email': 'officer1@lms.com.kh',
                'phone_number': '012 345 678',
                'national_id': '010123456',
                'role': User.Role.OFFICER,
                'is_staff': True,
            }
        )
        officer_user.set_password('pass123')
        officer_user.save()
        OfficerProfile.objects.get_or_create(
            user=officer_user,
            defaults={
                'employee_id': 'OFF-0824',
                'branch': 'Head Office - Phnom Penh',
                'department': 'Credit Underwriting',
                'phone': '012 345 678',
            }
        )

        borrower1, _ = User.objects.get_or_create(
            username='borrower1',
            defaults={
                'first_name': 'វណ្ណៈ',
                'last_name': 'កែវ',
                'email': 'vannak@gmail.com',
                'phone_number': '098 765 432',
                'national_id': '010987654',
                'role': User.Role.BORROWER,
            }
        )
        borrower1.set_password('pass123')
        borrower1.save()
        BorrowerProfile.objects.get_or_create(
            user=borrower1,
            defaults={
                'monthly_income': Decimal('2500.00'),
                'occupation': 'Business Owner',
                'employer': 'Keo Mart Electronics',
                'address': 'Street 271, Sangkat Boeng Tumpun, Khan Mean Chey, Phnom Penh',
                'credit_score': 720,
            }
        )

        borrower2, _ = User.objects.get_or_create(
            username='borrower2',
            defaults={
                'first_name': 'បុប្ផា',
                'last_name': 'រ័ត្ន',
                'email': 'bopha@gmail.com',
                'phone_number': '087 654 321',
                'national_id': '010876543',
                'role': User.Role.BORROWER,
            }
        )
        borrower2.set_password('pass123')
        borrower2.save()
        BorrowerProfile.objects.get_or_create(
            user=borrower2,
            defaults={
                'monthly_income': Decimal('1200.00'),
                'occupation': 'Marketing Executive',
                'employer': 'Angkor Media Corp',
                'address': 'Street 63, Sangkat Boeung Keng Kang 1, Phnom Penh',
                'credit_score': 680,
            }
        )

        p_sme, _ = LoanProduct.objects.get_or_create(
            code='SME',
            defaults={
                'name': 'ឥណទានអាជីវកម្ម SME (SME Business Loan)',
                'interest_rate': Decimal('10.50'),
                'currency': 'USD',
                'min_amount': Decimal('3000.00'),
                'max_amount': Decimal('50000.00'),
                'min_tenure_months': 12,
                'max_tenure_months': 36,
                'description': 'Working capital and asset expansion for registered small and medium enterprises.',
                'is_active': True,
            }
        )

        p_personal, _ = LoanProduct.objects.get_or_create(
            code='PERSONAL',
            defaults={
                'name': 'ឥណទានផ្ទាល់ខ្លួន (Personal Consumer Loan)',
                'interest_rate': Decimal('12.00'),
                'currency': 'USD',
                'min_amount': Decimal('500.00'),
                'max_amount': Decimal('10000.00'),
                'min_tenure_months': 6,
                'max_tenure_months': 24,
                'description': 'Unsecured consumer credit for household purchases and emergency needs.',
                'is_active': True,
            }
        )

        p_agri, _ = LoanProduct.objects.get_or_create(
            code='AGRI',
            defaults={
                'name': 'ឥណទានកសិកម្ម (Agriculture Loan)',
                'interest_rate': Decimal('9.50'),
                'currency': 'USD',
                'min_amount': Decimal('500.00'),
                'max_amount': Decimal('25000.00'),
                'min_tenure_months': 12,
                'max_tenure_months': 36,
                'description': 'Financing for agricultural inputs, machinery, irrigation, and harvest cycles.',
                'is_active': True,
            }
        )

        samples = [
            {
                'application_no': 'LN-202609-0012',
                'borrower': borrower1,
                'product': p_sme,
                'amount': Decimal('25000.00'),
                'currency': 'USD',
                'tenure_months': 24,
                'monthly_income': Decimal('2500.00'),
                'purpose': 'Stock expansion and inventory procurement for high season',
                'status': LoanApplication.Status.UNDER_REVIEW,
                'assigned_officer': officer_user,
                'officer_remarks': 'High quality borrower. CBC Score 720 (Grade A). Collateral pledged: Land Title #4812.',
            },
            {
                'application_no': 'LN-202609-0015',
                'borrower': borrower2,
                'product': p_personal,
                'amount': Decimal('5000.00'),
                'currency': 'USD',
                'tenure_months': 12,
                'monthly_income': Decimal('1200.00'),
                'purpose': 'Home renovation and new kitchen furnishings',
                'status': LoanApplication.Status.SUBMITTED,
                'assigned_officer': None,
                'officer_remarks': None,
            },
            {
                'application_no': 'LN-202609-0008',
                'borrower': borrower1,
                'product': p_personal,
                'amount': Decimal('3000.00'),
                'currency': 'USD',
                'tenure_months': 12,
                'monthly_income': Decimal('2500.00'),
                'purpose': 'Delivery motorcycle procurement for shop staff',
                'status': LoanApplication.Status.APPROVED,
                'approved_at': timezone.now(),
                'assigned_officer': officer_user,
                'officer_remarks': 'Approved with 12.00% annual rate. DTI ratio within 20% limit.',
            },
            {
                'application_no': 'LN-202609-0003',
                'borrower': borrower2,
                'product': p_agri,
                'amount': Decimal('4000.00'),
                'currency': 'USD',
                'tenure_months': 18,
                'monthly_income': Decimal('1200.00'),
                'purpose': 'Organic fertilizer and greenhouse drip lines',
                'status': LoanApplication.Status.REJECTED,
                'assigned_officer': officer_user,
                'officer_remarks': 'Declined due to existing debt-to-income ratio exceeding NBC prudential guidelines.',
            },
            {
                'application_no': 'LN-202609-0001',
                'borrower': borrower1,
                'product': p_sme,
                'amount': Decimal('10000.00'),
                'currency': 'USD',
                'tenure_months': 12,
                'monthly_income': Decimal('2500.00'),
                'purpose': 'Working capital and POS terminal upgrades',
                'status': LoanApplication.Status.APPROVED,
                'approved_at': timezone.now(),
                'assigned_officer': officer_user,
                'officer_remarks': 'Approved and scheduled for immediate disbursement.',
            },
        ]

        app_map = {}
        for s in samples:
            app, _ = LoanApplication.objects.update_or_create(
                application_no=s['application_no'],
                defaults=s
            )
            app_map[s['application_no']] = app

        Collateral.objects.update_or_create(
            loan=app_map['LN-202609-0012'],
            title_deed_number='No. 4812/MeanChey',
            defaults={
                'collateral_type': 'Land Title',
                'estimated_valuation': Decimal('48000.00'),
                'description': 'Hard title deed for residential & commercial shop-house in Sangkat Boeng Tumpun'
            }
        )

        Collateral.objects.update_or_create(
            loan=app_map['LN-202609-0008'],
            title_deed_number='PP-2BD-8899',
            defaults={
                'collateral_type': 'Vehicle',
                'estimated_valuation': Decimal('4500.00'),
                'description': '2024 Honda Scoopy Prestige registration card'
            }
        )

        Collateral.objects.update_or_create(
            loan=app_map['LN-202609-0001'],
            title_deed_number='No. 1109/ToulKork',
            defaults={
                'collateral_type': 'Land Title',
                'estimated_valuation': Decimal('22000.00'),
                'description': 'Commercial plot deed in Sangkat Boeng Kak 2, Khan Toul Kork'
            }
        )

        app_active = app_map['LN-202609-0001']
        execute_disbursal(app_active, officer=officer_user)

        first_inst = app_active.installments.filter(sequence_number=1).first()
        if first_inst:
            first_inst.status = LoanInstallment.Status.PAID
            first_inst.paid_at = timezone.now() - datetime.timedelta(days=28)
            first_inst.save()
            PaymentReceipt.objects.update_or_create(
                installment=first_inst,
                defaults={
                    'loan': app_active,
                    'payer': app_active.borrower,
                    'transaction_reference': 'TXN-KHQR-260901-01',
                    'amount': first_inst.total_installment_emi,
                    'currency': app_active.currency,
                    'payment_method': PaymentReceipt.PaymentMethod.BAKONG_KHQR,
                    'status': PaymentReceipt.Status.VERIFIED,
                    'verified_by': officer_user,
                    'verified_at': timezone.now() - datetime.timedelta(days=28),
                    'officer_notes': 'Settled instantly via Bakong KHQR QR scan.'
                }
            )

        second_inst = app_active.installments.filter(sequence_number=2).first()
        if second_inst:
            second_inst.status = LoanInstallment.Status.VERIFYING
            second_inst.save()
            PaymentReceipt.objects.update_or_create(
                installment=second_inst,
                defaults={
                    'loan': app_active,
                    'payer': app_active.borrower,
                    'transaction_reference': 'TXN-SLIP-260926-02',
                    'amount': second_inst.total_installment_emi,
                    'currency': app_active.currency,
                    'payment_method': PaymentReceipt.PaymentMethod.BAKONG_KHQR,
                    'status': PaymentReceipt.Status.PENDING,
                    'officer_notes': 'Borrower uploaded Bakong mobile transfer slip for verification.'
                }
            )

        app_overdue = app_map['LN-202609-0008']
        execute_disbursal(app_overdue, officer=officer_user)
        inst_od = app_overdue.installments.filter(sequence_number=1).first()
        if inst_od:
            inst_od.due_date = timezone.now().date() - datetime.timedelta(days=45)
            inst_od.status = LoanInstallment.Status.OVERDUE
            inst_od.save()

        for target_log in [
            (
                app_map['LN-202609-0012'],
                LoanApplication.Status.SUBMITTED,
                LoanApplication.Status.UNDER_REVIEW,
                'Application received. Requesting CBC credit bureau check.'
            ),
            (
                app_map['LN-202609-0008'],
                LoanApplication.Status.APPROVED,
                LoanApplication.Status.ACTIVE,
                'Disbursed and schedule activated. Installment #1 currently past due.'
            ),
            (
                app_map['LN-202609-0003'],
                LoanApplication.Status.SUBMITTED,
                LoanApplication.Status.REJECTED,
                'Declined due to debt-to-income ratio exceeding NBC limits.'
            ),
        ]:
            loan_obj, f_stat, t_stat, note = target_log
            if not ActionLog.objects.filter(loan=loan_obj, from_status=f_stat, to_status=t_stat).exists():
                ActionLog.objects.create(
                    loan=loan_obj,
                    changed_by=officer_user,
                    from_status=f_stat,
                    to_status=t_stat,
                    action_notes=note
                )

        self.stdout.write(self.style.SUCCESS('Successfully seeded demo users, products, applications, collaterals, active installments, and payment receipts!'))
