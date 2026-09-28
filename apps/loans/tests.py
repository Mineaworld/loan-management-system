import datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User, BorrowerProfile, OfficerProfile
from apps.loans.forms import LoanApplicationForm
from apps.loans.models import LoanProduct, LoanApplication, Collateral, ActionLog, LoanInstallment, PaymentReceipt
from apps.loans.services import (
    calculate_cbc_score,
    generate_amortization_schedule,
    execute_disbursal,
    record_repayment,
    process_slip_upload,
    verify_repayment_receipt,
    calculate_nbc_provisioning,
    calculate_delinquency_metrics,
    generate_report_csv,
)


class LoanProductAndAmortizationTest(TestCase):
    def setUp(self):
        self.sme_product = LoanProduct.objects.create(
            name='SME Business Loan',
            code='SME',
            interest_rate=Decimal('10.50'),
            currency='USD',
            min_amount=Decimal('3000.00'),
            max_amount=Decimal('50000.00'),
            min_tenure_months=12,
            max_tenure_months=36
        )

        self.borrower = User.objects.create_user(
            username='borrower_test',
            password='password123',
            role=User.Role.BORROWER
        )
        BorrowerProfile.objects.create(user=self.borrower)

    def test_product_str(self):
        self.assertIn('SME Business Loan', str(self.sme_product))

    def test_reducing_balance_emi_calculation(self):
        """
        Verify exact reducing balance Equal Monthly Installment formula:
        P = $10,000, R = 10.50% p.a., n = 24 months.
        Expected EMI = $463.80
        Expected Total Interest = $1,131.20
        Expected Total Repayment = $11,131.20
        """
        app = LoanApplication.objects.create(
            application_no='LN-TEST-0001',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('10000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('2500.00'),
            purpose='Equipment Purchase',
            status=LoanApplication.Status.SUBMITTED
        )

        self.assertEqual(app.emi, Decimal('463.76'))
        self.assertEqual(app.total_repayable, Decimal('11130.24'))
        self.assertEqual(app.total_interest, Decimal('1130.24'))

    def test_boundary_validation_in_model(self):
        under_min_app = LoanApplication(
            application_no='LN-TEST-UNDER',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('1000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('2500.00'),
            purpose='Test'
        )
        with self.assertRaises(ValidationError):
            under_min_app.clean()

        over_max_app = LoanApplication(
            application_no='LN-TEST-OVER',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('60000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('2500.00'),
            purpose='Test'
        )
        with self.assertRaises(ValidationError):
            over_max_app.clean()

    def test_auto_generated_application_no_on_model_create(self):
        app = LoanApplication.objects.create(
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('5000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('2000.00'),
            purpose='Auto no test',
            status=LoanApplication.Status.SUBMITTED
        )
        self.assertTrue(app.application_no.startswith('LN-'))
        self.assertRegex(app.application_no, r'^LN-\d{6}-\d{4}$')

    def test_emi_handles_zero_or_none_tenure(self):
        app = LoanApplication(
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('5000.00'),
            currency='USD',
            tenure_months=0,
            monthly_income=Decimal('2000.00'),
        )
        self.assertEqual(app.emi, Decimal('0.00'))
        self.assertEqual(app.total_repayable, Decimal('0.00'))
        self.assertEqual(app.total_interest, Decimal('0.00'))


class LoanViewsTest(TestCase):
    def setUp(self):
        self.client = Client()

        self.sme_product = LoanProduct.objects.create(
            name='SME Business Loan',
            code='SME',
            interest_rate=Decimal('10.50'),
            currency='USD',
            min_amount=Decimal('3000.00'),
            max_amount=Decimal('50000.00'),
            min_tenure_months=12,
            max_tenure_months=36
        )

        self.borrower = User.objects.create_user(
            username='borrower_view_test',
            password='password123',
            first_name='Vannak',
            last_name='Keo',
            role=User.Role.BORROWER,
            phone_number='012345678'
        )
        BorrowerProfile.objects.create(user=self.borrower)

        self.officer = User.objects.create_user(
            username='officer_view_test',
            password='password123',
            first_name='Sokha',
            last_name='Chhay',
            role=User.Role.OFFICER
        )
        OfficerProfile.objects.create(user=self.officer)

        self.app1 = LoanApplication.objects.create(
            application_no='LN-202609-0012',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('25000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('2500.00'),
            purpose='Stock expansion',
            status=LoanApplication.Status.UNDER_REVIEW
        )

    def test_borrower_portal_view(self):
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.get(reverse('loans:borrower_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ឥណទានរបស់ខ្ញុំ')
        self.assertContains(response, 'SME Business Loan')

    def test_borrower_submit_application(self):
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.post(reverse('loans:borrower_portal'), {
            'product': self.sme_product.id,
            'amount': '15000.00',
            'currency': 'USD',
            'tenure_months': '24',
            'monthly_income': '3000.00',
            'purpose': 'New branch opening',
        })
        self.assertRedirects(response, reverse('loans:borrower_portal'))
        new_app = LoanApplication.objects.filter(purpose='New branch opening').first()
        self.assertIsNotNone(new_app)
        self.assertEqual(new_app.status, LoanApplication.Status.SUBMITTED)
        self.assertTrue(new_app.application_no.startswith('LN-'))

    def test_borrower_submit_invalid_boundary_rejected(self):
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.post(reverse('loans:borrower_portal'), {
            'product': self.sme_product.id,
            'amount': '1000.00',
            'currency': 'USD',
            'tenure_months': '24',
            'monthly_income': '3000.00',
            'purpose': 'Invalid amount',
        })
        self.assertFalse(LoanApplication.objects.filter(purpose='Invalid amount').exists())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_section'], 'sec-apply')

    def test_borrower_submit_ajax_success(self):
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.post(
            reverse('loans:borrower_portal'),
            {
                'product': self.sme_product.id,
                'amount': '18000.00',
                'currency': 'USD',
                'tenure_months': '24',
                'monthly_income': '3500.00',
                'purpose': 'Working capital expansion',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('redirect_url'))
        self.assertIn('LN-', data.get('message'))

    def test_borrower_submit_ajax_invalid(self):
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.post(
            reverse('loans:borrower_portal'),
            {
                'product': self.sme_product.id,
                'amount': '100.00',  # below minimum
                'currency': 'USD',
                'tenure_months': '24',
                'monthly_income': '0',
                'purpose': 'Test invalid',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertTrue(len(data.get('errors')) > 0)
        self.assertIn('amount', data.get('field_errors'))

    def test_officer_dashboard_view(self):
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.get(reverse('loans:officer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LN-202609-0012')
        self.assertContains(response, 'Vannak Keo')

    def test_officer_search_filter(self):
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.get(reverse('loans:officer_dashboard') + '?q=Vannak')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LN-202609-0012')

        response_empty = self.client.get(reverse('loans:officer_dashboard') + '?q=NonExistentPerson')
        self.assertEqual(response_empty.status_code, 200)
        self.assertNotContains(response_empty, 'LN-202609-0012')

    def test_officer_status_filter(self):
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.get(reverse('loans:officer_dashboard') + '?status=UNDER_REVIEW')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LN-202609-0012')

        response_other = self.client.get(reverse('loans:officer_dashboard') + '?status=REJECTED')
        self.assertEqual(response_other.status_code, 200)
        self.assertNotContains(response_other, 'LN-202609-0012')

    def test_officer_approve_application(self):
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.post(reverse('loans:officer_dashboard'), {
            'application_id': self.app1.id,
            'action': 'APPROVE',
            'remarks': 'Approved by senior officer.'
        })
        self.assertRedirects(response, reverse('loans:officer_dashboard'))
        self.app1.refresh_from_db()
        self.assertEqual(self.app1.status, LoanApplication.Status.APPROVED)
        self.assertEqual(self.app1.assigned_officer, self.officer)

    def test_officer_reject_application(self):
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.post(reverse('loans:officer_dashboard'), {
            'application_id': self.app1.id,
            'action': 'REJECT',
            'remarks': 'Declined due to risk.'
        })
        self.assertRedirects(response, reverse('loans:officer_dashboard'))
        self.app1.refresh_from_db()
        self.assertEqual(self.app1.status, LoanApplication.Status.REJECTED)

    def test_unicode_and_emojis_in_loan_application(self):
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.post(reverse('loans:borrower_portal'), {
            'product': self.sme_product.id,
            'amount': '12000.00',
            'currency': 'USD',
            'tenure_months': '24',
            'monthly_income': '3000.00',
            'purpose': 'ទិញសម្ភារៈអាជីវកម្ម & គ្រឿងម៉ាស៊ីនទំនើប 🚀 🇰🇭 💯',
        })
        self.assertRedirects(response, reverse('loans:borrower_portal'))
        app = LoanApplication.objects.filter(amount=Decimal('12000.00')).first()
        self.assertIsNotNone(app)
        self.assertIn('🚀', app.purpose)

    def test_update_application_status_api(self):
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.post(
            reverse('loans:update_status_api', kwargs={'pk': self.app1.id}),
            {'status': 'APPROVED', 'remarks': 'API Approval ✅'}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_status'], 'APPROVED')
        self.app1.refresh_from_db()
        self.assertEqual(self.app1.status, LoanApplication.Status.APPROVED)
        self.assertEqual(self.app1.officer_remarks, 'API Approval ✅')

    def test_borrower_portal_empty_state_without_loans(self):
        new_borrower = User.objects.create_user(
            username='fresh_borrower',
            password='password123',
            role=User.Role.BORROWER
        )
        BorrowerProfile.objects.create(user=new_borrower)
        self.client.login(username='fresh_borrower', password='password123')
        response = self.client.get(reverse('loans:borrower_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'លោកអ្នកមិនទាន់មានឥណទានសកម្មនៅឡើយទេ')
        self.assertNotContains(response, '$ 23,110.27')
        self.assertNotContains(response, '$ 25,000.00')

    def test_borrower_portal_displays_all_user_applications(self):
        app2 = LoanApplication.objects.create(
            application_no='LN-202609-0099',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('8000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('2500.00'),
            purpose='App 2 purpose',
            status=LoanApplication.Status.SUBMITTED
        )
        self.client.login(username='borrower_view_test', password='password123')
        response = self.client.get(reverse('loans:borrower_portal'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LN-202609-0012')
        self.assertContains(response, 'LN-202609-0099')

    def test_officer_dashboard_active_portfolio_segregation(self):
        approved_app = LoanApplication.objects.create(
            application_no='LN-APPROVED-1',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('10000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('2500.00'),
            purpose='Approved SME Loan',
            status=LoanApplication.Status.APPROVED
        )
        rejected_app = LoanApplication.objects.create(
            application_no='LN-REJECTED-1',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('4000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('2500.00'),
            purpose='Rejected Loan',
            status=LoanApplication.Status.REJECTED
        )
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.get(reverse('loans:officer_dashboard'))
        self.assertEqual(response.status_code, 200)
        active_loans = list(response.context['active_loans'])
        self.assertIn(approved_app, active_loans)
        self.assertNotIn(rejected_app, active_loans)
        self.assertNotIn(self.app1, active_loans)

    def test_officer_review_application_action(self):
        submitted_app = LoanApplication.objects.create(
            application_no='LN-SUBMITTED-1',
            borrower=self.borrower,
            product=self.sme_product,
            amount=Decimal('7000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('2500.00'),
            purpose='Review test',
            status=LoanApplication.Status.SUBMITTED
        )
        self.client.login(username='officer_view_test', password='password123')
        response = self.client.post(reverse('loans:officer_dashboard'), {
            'application_id': submitted_app.id,
            'action': 'REVIEW'
        })
        self.assertRedirects(response, reverse('loans:officer_dashboard'))
        submitted_app.refresh_from_db()
        self.assertEqual(submitted_app.status, LoanApplication.Status.UNDER_REVIEW)
        self.assertEqual(submitted_app.assigned_officer, self.officer)

    def test_no_prototype_switchers_in_templates(self):
        self.client.login(username='borrower_view_test', password='password123')
        b_resp = self.client.get(reverse('loans:borrower_portal'))
        self.assertNotContains(b_resp, 'Switch to Officer')
        self.assertNotContains(b_resp, 'btn-switch-portal')

        self.client.login(username='officer_view_test', password='password123')
        o_resp = self.client.get(reverse('loans:officer_dashboard'))
        self.assertNotContains(o_resp, 'Switch to Borrower')
        self.assertNotContains(o_resp, 'btn-switch-portal')


class SimulatedCBCScoreTest(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(
            username='cbc_borrower',
            password='password123',
            role=User.Role.BORROWER
        )
        self.profile = BorrowerProfile.objects.create(
            user=self.borrower,
            credit_score=720,
            monthly_income=Decimal('3000.00')
        )
        self.product = LoanProduct.objects.create(
            name='SME Business Loan',
            code='SME_CBC',
            interest_rate=Decimal('10.50'),
            currency='USD',
            min_amount=Decimal('1000.00'),
            max_amount=Decimal('50000.00'),
            min_tenure_months=6,
            max_tenure_months=36
        )

    def test_cbc_score_with_strong_profile_and_collateral(self):
        """
        Base score: 720.
        Amount: $10,000, 24 months -> EMI: $463.76.
        Income: $3,000 -> DTI = 15.46% (<=30% -> +20).
        Collateral: $20,000 -> CCR = 200% (>=150% -> +20).
        Expected final score = 720 + 20 + 20 = 760 -> Grade A.
        """
        app = LoanApplication.objects.create(
            application_no='LN-CBC-0001',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('10000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('3000.00'),
            purpose='Shop Expansion'
        )
        Collateral.objects.create(
            loan=app,
            collateral_type='Land Title',
            title_deed_number='TD-101',
            estimated_valuation=Decimal('20000.00')
        )

        res = calculate_cbc_score(app)
        self.assertEqual(res['cbc_score'], 760)
        self.assertEqual(res['risk_grade'], 'A')
        self.assertEqual(res['dti'], Decimal('15.46'))
        self.assertEqual(res['collateral_coverage'], Decimal('200.00'))
        self.assertEqual(res['total_collateral'], Decimal('20000.00'))
        self.assertIn('Highly Recommended', res['recommendation'])

    def test_cbc_score_high_risk_and_no_collateral(self):
        """
        Base score: 500.
        Amount: $20,000, 12 months -> EMI: $1762.91.
        Income: $1,000 -> DTI = 176.29% (>50% -> -40).
        Collateral: 0 -> CCR = 0% (<50% -> -10).
        Expected final score = 500 - 40 - 10 = 450 -> Grade D (High Risk).
        """
        self.profile.credit_score = 500
        self.profile.save()

        app = LoanApplication.objects.create(
            application_no='LN-CBC-0002',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('20000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('1000.00'),
            purpose='Emergency'
        )

        res = calculate_cbc_score(app)
        self.assertEqual(res['cbc_score'], 450)
        self.assertEqual(res['risk_grade'], 'D')
        self.assertTrue(res['dti'] > Decimal('50.00'))
        self.assertEqual(res['collateral_coverage'], Decimal('0.00'))
        self.assertIn('High Risk', res['recommendation'])

    def test_cbc_score_clamping_limits(self):
        """Ensure score is strictly bounded between 300 and 850."""
        self.profile.credit_score = 845
        self.profile.save()
        app_high = LoanApplication.objects.create(
            application_no='LN-CBC-HIGH',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('5000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('5000.00'),
            purpose='Ceiling test'
        )
        Collateral.objects.create(
            loan=app_high,
            collateral_type='Land Title',
            estimated_valuation=Decimal('50000.00')
        )
        res_high = calculate_cbc_score(app_high)
        self.assertLessEqual(res_high['cbc_score'], 850)

        self.profile.credit_score = 310
        self.profile.save()
        app_low = LoanApplication.objects.create(
            application_no='LN-CBC-LOW',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('50000.00'),
            currency='USD',
            tenure_months=6,
            monthly_income=Decimal('500.00'),
            purpose='Floor test'
        )
        res_low = calculate_cbc_score(app_low)
        self.assertGreaterEqual(res_low['cbc_score'], 300)


class NBCAmortizationEngineTest(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(
            username='amort_borrower',
            password='password123',
            role=User.Role.BORROWER
        )
        self.product = LoanProduct.objects.create(
            name='SME Business Loan',
            code='SME_AMORT',
            interest_rate=Decimal('10.50'),
            currency='USD',
            min_amount=Decimal('1000.00'),
            max_amount=Decimal('100000.00'),
            min_tenure_months=6,
            max_tenure_months=36
        )

    def test_amortization_schedule_zero_reconciliation_24_months(self):
        """
        Verify that 24-month schedule:
        1. Contains exactly 24 periods.
        2. Sum of all principal components equals initial loan amount ($10,000.00).
        3. Final period 24 remaining balance is strictly Decimal('0.00').
        4. Each period interest is calculated on prior remaining balance.
        """
        app = LoanApplication.objects.create(
            application_no='LN-AMORT-24',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('10000.00'),
            currency='USD',
            tenure_months=24,
            monthly_income=Decimal('3000.00'),
            purpose='Equipment'
        )

        schedule = generate_amortization_schedule(app)
        self.assertEqual(len(schedule), 24)

        total_principal_paid = sum(item['principal_component'] for item in schedule)
        self.assertEqual(total_principal_paid, Decimal('10000.00'))

        last_period = schedule[-1]
        self.assertEqual(last_period['sequence_number'], 24)
        self.assertEqual(last_period['remaining_balance'], Decimal('0.00'))

        for i in range(len(schedule) - 1):
            self.assertLess(schedule[i]['due_date'], schedule[i+1]['due_date'])

    def test_amortization_schedule_zero_reconciliation_36_months(self):
        """Verify 36-month loan with $25,000 reconciles to strictly Decimal('0.00')."""
        app = LoanApplication.objects.create(
            application_no='LN-AMORT-36',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('25000.00'),
            currency='USD',
            tenure_months=36,
            monthly_income=Decimal('4000.00'),
            purpose='Warehouse expansion'
        )

        schedule = generate_amortization_schedule(app)
        self.assertEqual(len(schedule), 36)
        total_principal = sum(item['principal_component'] for item in schedule)
        self.assertEqual(total_principal, Decimal('25000.00'))
        self.assertEqual(schedule[-1]['remaining_balance'], Decimal('0.00'))

    def test_amortization_schedule_khr_currency(self):
        """Verify KHR schedule rounds to whole numbers and reconciles to Decimal('0')."""
        khr_product = LoanProduct.objects.create(
            name='Agri KHR Loan',
            code='AGRI_KHR',
            interest_rate=Decimal('9.50'),
            currency='KHR',
            min_amount=Decimal('1000000.00'),
            max_amount=Decimal('100000000.00'),
            min_tenure_months=6,
            max_tenure_months=24
        )
        app = LoanApplication.objects.create(
            application_no='LN-AMORT-KHR',
            borrower=self.borrower,
            product=khr_product,
            amount=Decimal('40000000.00'),
            currency='KHR',
            tenure_months=12,
            monthly_income=Decimal('5000000.00'),
            purpose='Fertilizer'
        )

        schedule = generate_amortization_schedule(app)
        self.assertEqual(len(schedule), 12)
        total_principal = sum(item['principal_component'] for item in schedule)
        self.assertEqual(total_principal, Decimal('40000000.00'))
        self.assertEqual(schedule[-1]['remaining_balance'], Decimal('0'))

    def test_amortization_schedule_empty_on_zero_tenure(self):
        app = LoanApplication(
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('5000.00'),
            currency='USD',
            tenure_months=0
        )
        schedule = generate_amortization_schedule(app)
        self.assertEqual(schedule, [])


class UnderwritingActionLogAndDisbursalTest(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(
            username='uw_borrower',
            password='password123',
            role=User.Role.BORROWER
        )
        BorrowerProfile.objects.create(user=self.borrower)

        self.officer = User.objects.create_user(
            username='uw_officer',
            password='password123',
            role=User.Role.OFFICER
        )
        OfficerProfile.objects.create(user=self.officer)

        self.product = LoanProduct.objects.create(
            name='Consumer Loan',
            code='CONS_UW',
            interest_rate=Decimal('12.00'),
            currency='USD',
            min_amount=Decimal('500.00'),
            max_amount=Decimal('10000.00'),
            min_tenure_months=6,
            max_tenure_months=24
        )

        self.app = LoanApplication.objects.create(
            application_no='LN-UW-0001',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('5000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('1500.00'),
            purpose='Consumer purchase',
            status=LoanApplication.Status.SUBMITTED
        )

    def test_execute_disbursal_creates_persistent_installments(self):
        """
        Disbursal workflow:
        1. Loan must be APPROVED first.
        2. execute_disbursal transitions to ACTIVE, records ActionLog, and bulk creates 12 installments.
        """
        self.app.status = LoanApplication.Status.APPROVED
        self.app.approved_at = timezone.now()
        self.app.save()

        installments = execute_disbursal(self.app, officer=self.officer)
        self.app.refresh_from_db()

        self.assertEqual(self.app.status, LoanApplication.Status.ACTIVE)
        self.assertIsNotNone(self.app.disbursed_at)
        self.assertEqual(self.app.assigned_officer, self.officer)

        log = ActionLog.objects.filter(loan=self.app).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.from_status, LoanApplication.Status.APPROVED)
        self.assertEqual(log.to_status, LoanApplication.Status.ACTIVE)
        self.assertEqual(log.changed_by, self.officer)

        self.assertEqual(len(installments), 12)
        db_installments = list(LoanInstallment.objects.filter(loan=self.app).order_by('sequence_number'))
        self.assertEqual(len(db_installments), 12)
        self.assertEqual(db_installments[0].sequence_number, 1)
        self.assertEqual(db_installments[0].status, LoanInstallment.Status.PENDING)
        self.assertEqual(db_installments[-1].sequence_number, 12)
        self.assertEqual(db_installments[-1].remaining_balance, Decimal('0.00'))

    def test_disburse_unapproved_loan_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            execute_disbursal(self.app, officer=self.officer)

        self.app.status = LoanApplication.Status.REJECTED
        self.app.save()
        with self.assertRaises(ValidationError):
            execute_disbursal(self.app, officer=self.officer)

        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()
        execute_disbursal(self.app, officer=self.officer, notes='Initial disbursal.')
        self.assertEqual(self.app.status, LoanApplication.Status.ACTIVE)

        with self.assertRaises(ValidationError):
            execute_disbursal(self.app, officer=self.officer)

        unsaved = LoanApplication(borrower=self.borrower, product=self.product, amount=Decimal('1000.00'), tenure_months=12)
        with self.assertRaises(ValidationError):
            execute_disbursal(unsaved, officer=self.officer)


class Phase2ViewsAndAPITest(TestCase):
    def setUp(self):
        self.client = Client()

        self.borrower = User.objects.create_user(
            username='phase2_borrower',
            password='password123',
            first_name='Vannak',
            last_name='Keo',
            role=User.Role.BORROWER
        )
        self.borrower_profile = BorrowerProfile.objects.create(
            user=self.borrower,
            credit_score=720,
            monthly_income=Decimal('2500.00')
        )

        self.officer = User.objects.create_user(
            username='phase2_officer',
            password='password123',
            role=User.Role.OFFICER
        )
        OfficerProfile.objects.create(user=self.officer)

        self.product = LoanProduct.objects.create(
            name='SME Business Loan',
            code='SME_P2',
            interest_rate=Decimal('10.50'),
            currency='USD',
            min_amount=Decimal('3000.00'),
            max_amount=Decimal('50000.00'),
            min_tenure_months=12,
            max_tenure_months=36
        )

        self.app = LoanApplication.objects.create(
            application_no='LN-P2-0001',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('10000.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('2500.00'),
            purpose='Branch equipment',
            status=LoanApplication.Status.SUBMITTED
        )

        Collateral.objects.create(
            loan=self.app,
            collateral_type='Land Title',
            title_deed_number='No. 4812/MeanChey',
            estimated_valuation=Decimal('20000.00'),
            description='Hard title deed'
        )

    def test_application_cbc_api(self):
        self.client.login(username='phase2_officer', password='password123')
        url = reverse('loans:application_cbc_api', kwargs={'pk': self.app.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['application_no'], 'LN-P2-0001')
        self.assertEqual(data['risk_grade'], 'A')
        self.assertGreaterEqual(data['cbc_score'], 700)
        self.assertEqual(data['collateral_coverage'], 200.0)
        self.assertEqual(len(data['collaterals']), 1)
        self.assertEqual(data['collaterals'][0]['title_deed'], 'No. 4812/MeanChey')

    def test_disburse_loan_api(self):
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()

        self.client.login(username='phase2_officer', password='password123')
        url = reverse('loans:disburse_loan_api', kwargs={'pk': self.app.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, LoanApplication.Status.ACTIVE)
        self.assertEqual(self.app.installments.count(), 12)

    def test_officer_dashboard_disburse_action_form(self):
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()

        self.client.login(username='phase2_officer', password='password123')
        response = self.client.post(reverse('loans:officer_dashboard'), {
            'application_id': self.app.id,
            'action': 'DISBURSE'
        })
        self.assertRedirects(response, reverse('loans:officer_dashboard'))

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, LoanApplication.Status.ACTIVE)
        self.assertEqual(self.app.installments.count(), 12)

    def test_borrower_portal_renders_persisted_installments(self):
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()
        execute_disbursal(self.app, officer=self.officer)

        self.client.login(username='phase2_borrower', password='password123')
        response = self.client.get(reverse('loans:borrower_portal'))
        self.assertEqual(response.status_code, 200)

        self.assertIn('installments', response.context)
        self.assertEqual(len(response.context['installments']), 12)
        self.assertIsNotNone(response.context['next_installment'])
        self.assertEqual(response.context['paid_count'], 0)
        self.assertEqual(response.context['total_count'], 12)
        self.assertEqual(response.context['progress_pct'], 0)

        self.assertContains(response, 'LN-P2-0001')
        self.assertContains(response, '#1')
        self.assertContains(response, '#12')

    def test_borrower_portal_with_first_installment_paid_points_to_next(self):
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()
        execute_disbursal(self.app, officer=self.officer)

        inst1 = self.app.installments.get(sequence_number=1)
        inst1.status = LoanInstallment.Status.PAID
        inst1.paid_at = timezone.now()
        inst1.save()

        self.client.login(username='phase2_borrower', password='password123')
        response = self.client.get(reverse('loans:borrower_portal'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['next_installment'].sequence_number, 2)
        self.assertEqual(response.context['paid_count'], 1)
        self.assertEqual(response.context['progress_pct'], 8)

        self.assertContains(response, 'LN-P2-0001-02')
        self.assertContains(response, 'Installment #2')

    def test_borrower_portal_tracks_overdue_installment_as_urgent_due(self):
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()
        execute_disbursal(self.app, officer=self.officer)

        inst1 = self.app.installments.get(sequence_number=1)
        inst1.status = LoanInstallment.Status.OVERDUE
        inst1.save()

        self.client.login(username='phase2_borrower', password='password123')
        response = self.client.get(reverse('loans:borrower_portal'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['next_installment'].sequence_number, 1)
        self.assertEqual(response.context['paid_count'], 0)
        self.assertEqual(response.context['remaining_principal'], Decimal('10000.00'))

    def test_calculate_cbc_score_unsaved_instance_and_zero_income(self):
        unsaved = LoanApplication(
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('5000.00'),
            tenure_months=12,
            monthly_income=Decimal('0.00'),
            purpose='Unsaved test'
        )
        res = calculate_cbc_score(unsaved)
        self.assertEqual(res['dti'], Decimal('100.00'))
        self.assertEqual(res['total_collateral'], Decimal('0.00'))
        self.assertEqual(res['collateral_coverage'], Decimal('0.00'))
        self.assertEqual(res['cbc_score'], 670)
        self.assertEqual(res['risk_grade'], 'B')

        low_borrower = User.objects.create_user(username='low_score_user', password='password123', role=User.Role.BORROWER)
        BorrowerProfile.objects.create(user=low_borrower, credit_score=500)
        unsaved_low = LoanApplication(
            borrower=low_borrower,
            product=self.product,
            amount=Decimal('5000.00'),
            tenure_months=12,
            monthly_income=Decimal('0.00'),
            purpose='Low score test'
        )
        res_low = calculate_cbc_score(unsaved_low)
        self.assertEqual(res_low['cbc_score'], 450)
        self.assertEqual(res_low['risk_grade'], 'D')

    def test_generate_amortization_schedule_zero_interest_rate(self):
        zero_prod = LoanProduct.objects.create(
            name='Zero Interest Promo',
            code='ZERO_INT',
            interest_rate=Decimal('0.00'),
            currency='USD',
            min_amount=Decimal('100.00'),
            max_amount=Decimal('10000.00'),
            min_tenure_months=6,
            max_tenure_months=24
        )
        zero_app = LoanApplication.objects.create(
            application_no='LN-ZERO-01',
            borrower=self.borrower,
            product=zero_prod,
            amount=Decimal('1200.00'),
            currency='USD',
            tenure_months=12,
            monthly_income=Decimal('2000.00'),
            purpose='Zero interest'
        )
        schedule = generate_amortization_schedule(zero_app)
        self.assertEqual(len(schedule), 12)
        total_p = sum(item['principal_component'] for item in schedule)
        total_i = sum(item['interest_component'] for item in schedule)
        self.assertEqual(total_p, Decimal('1200.00'))
        self.assertEqual(total_i, Decimal('0.00'))
        self.assertEqual(schedule[-1]['remaining_balance'], Decimal('0.00'))

    def test_officer_dashboard_first_app_in_context_and_buttons(self):
        self.client.login(username='phase2_officer', password='password123')
        response = self.client.get(reverse('loans:officer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('first_app', response.context)
        self.assertEqual(response.context['first_app'], self.app)
        self.assertContains(response, 'id="cbcBtnApprove"')
        self.assertContains(response, 'id="cbcBtnReview"')
        self.assertContains(response, 'id="cbcBtnReject"')

    def test_update_status_api_to_active_executes_disbursal(self):
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()

        self.client.login(username='phase2_officer', password='password123')
        url = reverse('loans:update_status_api', kwargs={'pk': self.app.id})
        response = self.client.post(url, {'status': 'ACTIVE', 'remarks': 'API Disbursal'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, LoanApplication.Status.ACTIVE)
        self.assertEqual(self.app.installments.count(), 12)


class Phase3FintechAndSettlementTest(TestCase):
    def setUp(self):
        self.borrower = User.objects.create_user(
            username='phase3_borrower',
            password='password123',
            role=User.Role.BORROWER,
            first_name='Vannak',
            last_name='Keo'
        )
        self.officer = User.objects.create_user(
            username='phase3_officer',
            password='password123',
            role=User.Role.OFFICER,
            first_name='Chan',
            last_name='Sophea'
        )
        self.product = LoanProduct.objects.create(
            name='SME Expansion',
            code='SME_P3',
            interest_rate=Decimal('10.50'),
            currency='USD',
            min_amount=Decimal('1000.00'),
            max_amount=Decimal('50000.00'),
            min_tenure_months=6,
            max_tenure_months=36
        )
        self.app = LoanApplication.objects.create(
            application_no='LN-P3-0001',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('6000.00'),
            currency='USD',
            tenure_months=6,
            monthly_income=Decimal('2500.00'),
            purpose='Fintech test'
        )
        self.app.status = LoanApplication.Status.APPROVED
        self.app.save()
        execute_disbursal(self.app, officer=self.officer)

    def test_record_repayment_settles_installment_and_creates_verified_receipt(self):
        inst1 = self.app.installments.get(sequence_number=1)
        updated_inst, receipt = record_repayment(
            installment=inst1,
            payment_method=PaymentReceipt.PaymentMethod.BAKONG_KHQR,
            payer=self.borrower
        )
        self.assertEqual(updated_inst.status, LoanInstallment.Status.PAID)
        self.assertIsNotNone(updated_inst.paid_at)
        self.assertEqual(receipt.status, PaymentReceipt.Status.VERIFIED)
        self.assertEqual(receipt.amount, inst1.total_installment_emi)
        self.assertEqual(receipt.payment_method, PaymentReceipt.PaymentMethod.BAKONG_KHQR)

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, LoanApplication.Status.ACTIVE)

    def test_record_repayment_already_paid_raises_validation_error(self):
        inst1 = self.app.installments.get(sequence_number=1)
        record_repayment(inst1, PaymentReceipt.PaymentMethod.BAKONG_KHQR, self.borrower)

        with self.assertRaises(ValidationError):
            record_repayment(inst1, PaymentReceipt.PaymentMethod.BAKONG_KHQR, self.borrower)

    def test_record_repayment_completes_loan_when_all_installments_paid(self):
        for inst in self.app.installments.all():
            record_repayment(inst, PaymentReceipt.PaymentMethod.BAKONG_KHQR, self.borrower)

        self.app.refresh_from_db()
        self.assertEqual(self.app.status, LoanApplication.Status.COMPLETED)
        self.assertEqual(self.app.installments.filter(status=LoanInstallment.Status.PAID).count(), 6)

    def test_process_slip_upload_marks_verifying_and_creates_pending_receipt(self):
        inst2 = self.app.installments.get(sequence_number=2)
        fake_file = SimpleUploadedFile("slip.jpg", b"fake_image_bytes", content_type="image/jpeg")

        receipt = process_slip_upload(
            installment=inst2,
            payer=self.borrower,
            slip_file=fake_file,
            transaction_ref='TXN-TEST-9988',
            notes='Test slip upload'
        )
        self.assertEqual(receipt.status, PaymentReceipt.Status.PENDING)
        self.assertEqual(receipt.transaction_reference, 'TXN-TEST-9988')
        inst2.refresh_from_db()
        self.assertEqual(inst2.status, LoanInstallment.Status.VERIFYING)

    def test_verify_repayment_receipt_approved(self):
        inst2 = self.app.installments.get(sequence_number=2)
        fake_file = SimpleUploadedFile("slip.jpg", b"fake_image_bytes", content_type="image/jpeg")
        receipt = process_slip_upload(inst2, self.borrower, fake_file)

        verified_rec = verify_repayment_receipt(receipt, self.officer, approved=True, notes='Valid transfer slip.')
        self.assertEqual(verified_rec.status, PaymentReceipt.Status.VERIFIED)
        self.assertEqual(verified_rec.verified_by, self.officer)
        inst2.refresh_from_db()
        self.assertEqual(inst2.status, LoanInstallment.Status.PAID)

    def test_verify_repayment_receipt_rejected(self):
        inst2 = self.app.installments.get(sequence_number=2)
        fake_file = SimpleUploadedFile("slip.jpg", b"fake_image_bytes", content_type="image/jpeg")
        receipt = process_slip_upload(inst2, self.borrower, fake_file)

        rejected_rec = verify_repayment_receipt(receipt, self.officer, approved=False, notes='Invalid account name.')
        self.assertEqual(rejected_rec.status, PaymentReceipt.Status.REJECTED)
        self.assertEqual(rejected_rec.verified_by, self.officer)
        inst2.refresh_from_db()
        self.assertEqual(inst2.status, LoanInstallment.Status.PENDING)

    def test_calculate_nbc_provisioning_and_delinquency_metrics(self):
        app2 = LoanApplication.objects.create(
            application_no='LN-P3-0002',
            borrower=self.borrower,
            product=self.product,
            amount=Decimal('4000.00'),
            currency='USD',
            tenure_months=6,
            monthly_income=Decimal('2500.00'),
            purpose='Delinquency test'
        )
        app2.status = LoanApplication.Status.APPROVED
        app2.save()
        execute_disbursal(app2, officer=self.officer)

        inst_overdue = app2.installments.get(sequence_number=1)
        inst_overdue.due_date = timezone.now().date() - datetime.timedelta(days=40)
        inst_overdue.status = LoanInstallment.Status.OVERDUE
        inst_overdue.save()

        prov = calculate_nbc_provisioning()
        self.assertGreaterEqual(prov['total_loans'], 2)
        self.assertGreater(prov['total_portfolio'], Decimal('0.00'))
        self.assertGreater(prov['total_provision'], Decimal('0.00'))

        special_mention_tier = next(t for t in prov['tiers'] if t['tier_key'] == 'SPECIAL_MENTION')
        self.assertGreaterEqual(special_mention_tier['loan_count'], 1)

        delinq = calculate_delinquency_metrics()
        self.assertGreater(delinq['par_30_balance'], Decimal('0.00'))
        self.assertGreater(delinq['par_30_ratio'], 0.0)

    def test_simulate_instant_pay_api_view(self):
        self.client.login(username='phase3_borrower', password='password123')
        inst1 = self.app.installments.get(sequence_number=1)
        url = reverse('loans:simulate_instant_pay')

        response = self.client.post(url, {'installment_id': inst1.id})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['status'], 'PAID')

        inst1.refresh_from_db()
        self.assertEqual(inst1.status, LoanInstallment.Status.PAID)

    def test_upload_payment_slip_view(self):
        self.client.login(username='phase3_borrower', password='password123')
        inst2 = self.app.installments.get(sequence_number=2)
        fake_file = SimpleUploadedFile("slip.jpg", b"fake_bytes", content_type="image/jpeg")

        url = reverse('loans:upload_payment_slip')
        response = self.client.post(url, {
            'installment_id': inst2.id,
            'slip_image': fake_file,
            'transaction_reference': 'TXN-SLIP-VIEW-01',
            'notes': 'Uploaded via web form'
        })
        self.assertEqual(response.status_code, 302)
        inst2.refresh_from_db()
        self.assertEqual(inst2.status, LoanInstallment.Status.VERIFYING)
        self.assertTrue(PaymentReceipt.objects.filter(transaction_reference='TXN-SLIP-VIEW-01').exists())

    def test_verify_receipt_api_endpoint(self):
        inst2 = self.app.installments.get(sequence_number=2)
        fake_file = SimpleUploadedFile("slip.jpg", b"fake_bytes", content_type="image/jpeg")
        receipt = process_slip_upload(inst2, self.borrower, fake_file)

        self.client.login(username='phase3_officer', password='password123')
        url = reverse('loans:verify_receipt', kwargs={'pk': receipt.id})
        response = self.client.post(url, {'notes': 'API Approved'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        receipt.refresh_from_db()
        self.assertEqual(receipt.status, PaymentReceipt.Status.VERIFIED)
        inst2.refresh_from_db()
        self.assertEqual(inst2.status, LoanInstallment.Status.PAID)

    def test_reject_receipt_api_endpoint(self):
        inst3 = self.app.installments.get(sequence_number=3)
        fake_file = SimpleUploadedFile("slip.jpg", b"fake_bytes", content_type="image/jpeg")
        receipt = process_slip_upload(inst3, self.borrower, fake_file)

        self.client.login(username='phase3_officer', password='password123')
        url = reverse('loans:reject_receipt', kwargs={'pk': receipt.id})
        response = self.client.post(url, {'notes': 'API Rejected'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        receipt.refresh_from_db()
        self.assertEqual(receipt.status, PaymentReceipt.Status.REJECTED)
        inst3.refresh_from_db()
        self.assertEqual(inst3.status, LoanInstallment.Status.PENDING)

    def test_nbc_provisioning_api_endpoint(self):
        self.client.login(username='phase3_officer', password='password123')
        url = reverse('loans:nbc_provisioning_api')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('tiers', data)
        self.assertEqual(len(data['tiers']), 5)
        self.assertIn('par_30_ratio', data)

    def test_export_report_csv_view_streaming(self):
        self.client.login(username='phase3_officer', password='password123')
        url = reverse('loans:export_report_csv')

        res_quality = self.client.get(url + '?type=asset_quality')
        self.assertEqual(res_quality.status_code, 200)
        self.assertEqual(res_quality['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment;', res_quality['Content-Disposition'])
        self.assertIn('NATIONAL BANK OF CAMBODIA', res_quality.content.decode('utf-8'))

        res_delinq = self.client.get(url + '?type=delinquency')
        self.assertEqual(res_delinq.status_code, 200)
        self.assertIn('PORTFOLIO-AT-RISK', res_delinq.content.decode('utf-8'))

        res_repay = self.client.get(url + '?type=repayments')
        self.assertEqual(res_repay.status_code, 200)
        self.assertIn('REPAYMENT RECONCILIATION', res_repay.content.decode('utf-8'))

    def test_borrower_payment_history_rendering(self):
        self.client.login(username='phase3_borrower', password='password123')
        inst1 = self.app.installments.get(sequence_number=1)
        record_repayment(inst1, PaymentReceipt.PaymentMethod.BAKONG_KHQR, self.borrower, reference='TXN-HIST-001')

        response = self.client.get(reverse('loans:borrower_portal') + '?tab=history')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sec-history" class="view-section active"')
        self.assertContains(response, 'TXN-HIST-001')
        self.assertContains(response, 'Bakong KHQR')
        self.assertContains(response, 'បានផ្ទៀងផ្ទាត់')

