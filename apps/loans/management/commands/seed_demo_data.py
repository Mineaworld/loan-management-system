import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import User, BorrowerProfile, OfficerProfile, Branch
from apps.loans.models import LoanProduct, LoanApplication, Collateral, ActionLog, LoanInstallment, PaymentReceipt
from apps.loans.services import execute_disbursal


class Command(BaseCommand):
    help = 'Seed demo branches, users, 6 loan products, sample applications, collaterals, and active installments'

    def handle(self, *args, **options):
        self.stdout.write('Seeding Sovanaphum Microfinance demo data...')

        # 1. Seed 5 Institutional Branches
        branches_data = [
            {
                'code': 'HO-PP',
                'name_km': 'ការិយាល័យកណ្តាល (ភ្នំពេញ)',
                'name_en': 'Head Office — Phnom Penh',
                'province': 'Phnom Penh',
                'phone': '023 999 001',
                'address': 'Building 168, Preah Norodom Blvd, Sangkat Tonle Bassac, Khan Chamkarmon, Phnom Penh'
            },
            {
                'code': 'BR-TK',
                'name_km': 'សាខាទួលគោក',
                'name_en': 'Toul Kork Urban Branch',
                'province': 'Phnom Penh',
                'phone': '023 999 002',
                'address': 'Street 289, Sangkat Boeung Kak 1, Khan Toul Kork, Phnom Penh'
            },
            {
                'code': 'BR-SR',
                'name_km': 'សាខាខេត្តសៀមរាប',
                'name_en': 'Siem Reap Provincial Branch',
                'province': 'Siem Reap',
                'phone': '063 999 003',
                'address': 'National Road 6, Sangkat Svay Dangkum, Krong Siem Reap'
            },
            {
                'code': 'BR-BTB',
                'name_km': 'សាខាខេត្តបាត់ដំបង',
                'name_en': 'Battambang Provincial Branch',
                'province': 'Battambang',
                'phone': '053 999 004',
                'address': 'Street 106, Sangkat Svay Por, Krong Battambang'
            },
            {
                'code': 'BR-KPC',
                'name_km': 'សាខាខេត្តកំពង់ចាម',
                'name_en': 'Kampong Cham Provincial Branch',
                'province': 'Kampong Cham',
                'phone': '042 999 005',
                'address': 'Preah Monivong St, Sangkat Veal Vong, Krong Kampong Cham'
            },
        ]
        branch_objs = {}
        for b_data in branches_data:
            br, _ = Branch.objects.update_or_create(code=b_data['code'], defaults=b_data)
            branch_objs[b_data['code']] = br
        ho_branch = branch_objs['HO-PP']

        # 2. Seed Users & Staff Profiles
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'System',
                'last_name': 'Admin',
                'email': 'admin@sovanaphum.com.kh',
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
                'email': 'officer1@sovanaphum.com.kh',
                'phone_number': '012 345 678',
                'national_id': '010123456',
                'role': User.Role.OFFICER,
                'is_staff': True,
            }
        )
        officer_user.set_password('pass123')
        officer_user.save()
        OfficerProfile.objects.update_or_create(
            user=officer_user,
            defaults={
                'employee_id': 'CO-0824',
                'branch': ho_branch,
                'department': 'Credit & Underwriting Department',
                'phone': '012 345 678',
                'desk_phone': '023 999 001',
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
        BorrowerProfile.objects.update_or_create(
            user=borrower1,
            defaults={
                'servicing_branch': ho_branch,
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
        BorrowerProfile.objects.update_or_create(
            user=borrower2,
            defaults={
                'servicing_branch': ho_branch,
                'monthly_income': Decimal('1200.00'),
                'occupation': 'Marketing Executive',
                'employer': 'Angkor Media Corp',
                'address': 'Street 63, Sangkat Boeung Keng Kang 1, Phnom Penh',
                'credit_score': 680,
            }
        )

        # 3. Seed 6 Cambodian Loan Products (Option 2 Matrix)
        products_data = [
            {
                'code': 'SME-01',
                'name': 'ឥណទានអាជីវកម្ម SME (SME Business Loan)',
                'interest_rate': Decimal('10.50'),
                'currency': 'USD',
                'min_amount': Decimal('3000.00'),
                'max_amount': Decimal('50000.00'),
                'min_tenure_months': 12,
                'max_tenure_months': 36,
                'description': 'Working capital and asset expansion for registered small and medium enterprises. Secured by land title deed.',
                'is_active': True,
            },
            {
                'code': 'PER-01',
                'name': 'ឥណទានផ្ទាល់ខ្លួន (Personal Consumer Loan)',
                'interest_rate': Decimal('12.00'),
                'currency': 'USD',
                'min_amount': Decimal('500.00'),
                'max_amount': Decimal('10000.00'),
                'min_tenure_months': 6,
                'max_tenure_months': 24,
                'description': 'Unsecured consumer credit for household purchases, appliances, and personal emergency needs.',
                'is_active': True,
            },
            {
                'code': 'AGR-01',
                'name': 'ឥណទានកសិកម្ម (Agriculture Loan)',
                'interest_rate': Decimal('9.50'),
                'currency': 'USD',
                'min_amount': Decimal('500.00'),
                'max_amount': Decimal('25000.00'),
                'min_tenure_months': 12,
                'max_tenure_months': 36,
                'description': 'Financing for agricultural inputs, machinery, tractor acquisition, irrigation, and harvest cycles.',
                'is_active': True,
            },
            {
                'code': 'AUT-01',
                'name': 'ឥណទានទិញយានយន្ត (Auto & Vehicle Loan)',
                'interest_rate': Decimal('10.00'),
                'currency': 'USD',
                'min_amount': Decimal('1000.00'),
                'max_amount': Decimal('30000.00'),
                'min_tenure_months': 12,
                'max_tenure_months': 48,
                'description': 'Automobile, pickup truck, and motorcycle financing secured by vehicle registration card (ID & chassis plate).',
                'is_active': True,
            },
            {
                'code': 'HOM-01',
                'name': 'ឥណទានគេហដ្ឋាន (Housing & Improvement)',
                'interest_rate': Decimal('8.50'),
                'currency': 'USD',
                'min_amount': Decimal('5000.00'),
                'max_amount': Decimal('100000.00'),
                'min_tenure_months': 24,
                'max_tenure_months': 60,
                'description': 'Residential property acquisition, renovation, and construction secured by registered hard title deed.',
                'is_active': True,
            },
            {
                'code': 'EDU-01',
                'name': 'ឥណទានការសិក្សា (Education & Tuition Loan)',
                'interest_rate': Decimal('7.50'),
                'currency': 'USD',
                'min_amount': Decimal('300.00'),
                'max_amount': Decimal('5000.00'),
                'min_tenure_months': 6,
                'max_tenure_months': 24,
                'description': 'Subsidized rate for university and vocational students. Requires student ID enrollment proof and co-signer.',
                'is_active': True,
            },
        ]
        product_objs = {}
        for p_data in products_data:
            p, _ = LoanProduct.objects.update_or_create(code=p_data['code'], defaults=p_data)
            product_objs[p_data['code']] = p

        # Clean up legacy duplicate aliases ('SME', 'PERSONAL', 'AGRI') and ensure deduplication
        legacy_code_map = {
            'SME': 'SME-01',
            'PERSONAL': 'PER-01',
            'AGRI': 'AGR-01',
        }
        for old_code, canonical_code in legacy_code_map.items():
            old_prod = LoanProduct.objects.filter(code=old_code).first()
            canonical_prod = product_objs.get(canonical_code)
            if old_prod and canonical_prod:
                LoanApplication.objects.filter(product=old_prod).update(product=canonical_prod)
                old_prod.delete()

        # Delete any orphan products not in official 6 products
        valid_codes = [p['code'] for p in products_data]
        for extra_prod in LoanProduct.objects.exclude(code__in=valid_codes):
            if not extra_prod.applications.exists():
                extra_prod.delete()

        p_sme = product_objs['SME-01']
        p_personal = product_objs['PER-01']
        p_agri = product_objs['AGR-01']
        p_auto = product_objs['AUT-01']
        p_edu = product_objs['EDU-01']

        # 4. Seed Sample Loan Applications with Branch and Officer Assignments
        samples = [
            {
                'application_no': 'LN-202609-0012',
                'borrower': borrower1,
                'product': p_sme,
                'branch': ho_branch,
                'amount': Decimal('25000.00'),
                'currency': 'USD',
                'tenure_months': 24,
                'monthly_income': Decimal('2500.00'),
                'purpose': 'Stock expansion and inventory procurement for high season',
                'status': LoanApplication.Status.UNDER_REVIEW,
                'assigned_officer': officer_user,  # In "My Covered Borrowers" queue
                'officer_remarks': 'High quality borrower. CBC Score 720 (Grade A). Collateral pledged: Land Title #4812.',
            },
            {
                'application_no': 'LN-202609-0015',
                'borrower': borrower2,
                'product': p_personal,
                'branch': ho_branch,
                'amount': Decimal('5000.00'),
                'currency': 'USD',
                'tenure_months': 12,
                'monthly_income': Decimal('1200.00'),
                'purpose': 'Home renovation and new kitchen furnishings',
                'status': LoanApplication.Status.SUBMITTED,
                'assigned_officer': None,  # In "Unassigned Applications" queue for 1-click claim demo
                'officer_remarks': None,
            },
            {
                'application_no': 'LN-202609-0008',
                'borrower': borrower1,
                'product': p_personal,
                'branch': ho_branch,
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
                'branch': branch_objs['BR-SR'],  # Siem Reap branch
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
                'branch': ho_branch,
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
            {
                'application_no': 'LN-202609-0020',
                'borrower': borrower1,
                'product': p_auto,
                'branch': ho_branch,
                'amount': Decimal('8500.00'),
                'currency': 'USD',
                'tenure_months': 24,
                'monthly_income': Decimal('2500.00'),
                'purpose': 'Used commercial delivery van acquisition',
                'status': LoanApplication.Status.SUBMITTED,
                'assigned_officer': None,  # Another unassigned application for demo
                'officer_remarks': None,
            },
            {
                'application_no': 'LN-202609-0025',
                'borrower': borrower2,
                'product': p_edu,
                'branch': branch_objs['BR-TK'],
                'amount': Decimal('1200.00'),
                'currency': 'USD',
                'tenure_months': 12,
                'monthly_income': Decimal('1200.00'),
                'purpose': 'University Year 4 Semester tuition fees and laptop financing',
                'status': LoanApplication.Status.SUBMITTED,
                'assigned_officer': None,
                'officer_remarks': None,
            },
        ]

        app_map = {}
        for s in samples:
            app, _ = LoanApplication.objects.update_or_create(
                application_no=s['application_no'],
                defaults=s
            )
            app_map[s['application_no']] = app

        # 5. Seed Collateral Records (Real Estate + Motor Vehicle)
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
            loan=app_map['LN-202609-0020'],
            title_deed_number='PP-2BC-7721',
            defaults={
                'collateral_type': 'Vehicle',
                'estimated_valuation': Decimal('12000.00'),
                'description': '2021 Hyundai Porter II commercial delivery truck (Chassis: KMFGB17HP...)'
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

        # 6. Disburse LN-202609-0001 and seed active installments & receipts
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

        # 7. Action Audit Logs
        for target_log in [
            (
                app_map['LN-202609-0012'],
                LoanApplication.Status.SUBMITTED,
                LoanApplication.Status.UNDER_REVIEW,
                'Application claimed by Credit Officer Sokha Chhay (CO-0824) for underwriting and CBC investigation.'
            ),
            (
                app_map['LN-202609-0008'],
                LoanApplication.Status.APPROVED,
                LoanApplication.Status.ACTIVE,
                'Disbursed and schedule activated by Credit Officer Sokha Chhay.'
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

        self.stdout.write(self.style.SUCCESS('Successfully seeded Sovanaphum Microfinance demo data (5 branches, 6 products, CO assignments)!'))
