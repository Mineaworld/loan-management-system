from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, BorrowerProfile, OfficerProfile, Branch
from apps.accounts.forms import BorrowerRegistrationForm, LoginForm


class UserModelTest(TestCase):
    def test_create_borrower_user(self):
        user = User.objects.create_user(
            username='test_borrower',
            password='password123',
            first_name='Vannak',
            last_name='Keo',
            role=User.Role.BORROWER,
            phone_number='012345678'
        )
        self.assertTrue(user.is_borrower)
        self.assertFalse(user.is_officer)
        self.assertFalse(user.is_admin_user)
        self.assertIn('Vannak Keo', str(user))

    def test_create_officer_user(self):
        user = User.objects.create_user(
            username='test_officer',
            password='password123',
            role=User.Role.OFFICER
        )
        self.assertFalse(user.is_borrower)
        self.assertTrue(user.is_officer)
        self.assertFalse(user.is_admin_user)

    def test_create_admin_user(self):
        user = User.objects.create_user(
            username='test_admin',
            password='password123',
            role=User.Role.ADMIN
        )
        self.assertTrue(user.is_admin_user)

    def test_profiles_relationship(self):
        b_user = User.objects.create_user(username='b_profile_test', password='password123', role=User.Role.BORROWER)
        b_profile = BorrowerProfile.objects.create(
            user=b_user,
            monthly_income=Decimal('2500.00'),
            occupation='Engineer'
        )
        self.assertEqual(b_user.borrower_profile.occupation, 'Engineer')
        self.assertEqual(b_user.borrower_profile.credit_score, 720)

        o_user = User.objects.create_user(username='o_profile_test', password='password123', role=User.Role.OFFICER)
        branch = Branch.objects.create(code='HO-PP', name_en='Phnom Penh Main', name_km='ភ្នំពេញ')
        o_profile = OfficerProfile.objects.create(
            user=o_user,
            employee_id='EMP-001',
            branch=branch
        )
        self.assertEqual(o_user.officer_profile.employee_id, 'EMP-001')
        self.assertEqual(o_user.officer_profile.branch.code, 'HO-PP')


class AuthViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.borrower = User.objects.create_user(
            username='borrower1',
            password='password123',
            role=User.Role.BORROWER,
            phone_number='098765432'
        )
        BorrowerProfile.objects.create(user=self.borrower)

        self.officer = User.objects.create_user(
            username='officer1',
            password='password123',
            role=User.Role.OFFICER,
            phone_number='012345678'
        )
        OfficerProfile.objects.create(user=self.officer)

    def test_get_auth_page(self):
        response = self.client.get(reverse('accounts:auth'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ចូលប្រើប្រាស់')
        self.assertContains(response, 'Sign In')

    def test_borrower_login_redirects_to_borrower_portal(self):
        response = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'LOGIN',
            'username': 'borrower1',
            'password': 'password123',
        })
        self.assertRedirects(response, reverse('borrower'))

    def test_borrower_phone_login(self):
        response = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'LOGIN',
            'username': '098765432',
            'password': 'password123',
        })
        self.assertRedirects(response, reverse('borrower'))

    def test_officer_login_redirects_to_officer_dashboard(self):
        response = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'LOGIN',
            'username': 'officer1',
            'password': 'password123',
        })
        self.assertRedirects(response, reverse('officer'))

    def test_invalid_login_shows_error(self):
        response = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'LOGIN',
            'username': 'borrower1',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(len(messages) > 0)

    def test_borrower_registration(self):
        response = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'REGISTER',
            'full_name': 'Sophea Pich',
            'phone_number': '077889900',
            'national_id': '020495837',
            'primary_currency': 'USD',
            'password': 'newpassword123',
            'confirm_password': 'newpassword123',
        })
        self.assertRedirects(response, reverse('borrower'))
        new_user = User.objects.filter(phone_number='077889900').first()
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.first_name, 'Sophea')
        self.assertEqual(new_user.role, User.Role.BORROWER)
        self.assertIsNotNone(new_user.borrower_profile)

    def test_unauthenticated_officer_access_redirects(self):
        response = self.client.get(reverse('officer'))
        self.assertRedirects(response, f"{reverse('accounts:auth')}?next=/officer/")

    def test_borrower_access_to_officer_dashboard_forbidden(self):
        self.client.login(username='borrower1', password='password123')
        response = self.client.get(reverse('officer'))
        self.assertRedirects(response, reverse('borrower'))

    def test_logout_redirects_to_auth(self):
        self.client.login(username='borrower1', password='password123')
        response = self.client.get(reverse('accounts:logout'))
        self.assertRedirects(response, reverse('accounts:auth'))

    def test_borrower_registration_duplicate_phone_rejected(self):
        response = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'REGISTER',
            'full_name': 'Duplicate User',
            'phone_number': '098765432',
            'national_id': '020495899',
            'primary_currency': 'USD',
            'password': 'newpassword123',
            'confirm_password': 'newpassword123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(phone_number='098765432').count(), 1)

    def test_borrower_registration_consecutive_users_without_conflict(self):
        self.client.post(reverse('accounts:auth'), {
            'auth_action': 'REGISTER',
            'full_name': 'User One',
            'phone_number': '011223344',
            'national_id': '020000001',
            'primary_currency': 'USD',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        response2 = self.client.post(reverse('accounts:auth'), {
            'auth_action': 'REGISTER',
            'full_name': 'User Two',
            'phone_number': '011 223 345',
            'national_id': '020000002',
            'primary_currency': 'KHR',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertRedirects(response2, reverse('borrower'))
        u1 = User.objects.filter(phone_number='011223344').first()
        u2 = User.objects.filter(phone_number='011 223 345').first()
        self.assertIsNotNone(u1)
        self.assertIsNotNone(u2)
        self.assertNotEqual(u1.username, u2.username)


class StaffManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.branch_ho = Branch.objects.create(
            code='HO-PP',
            name_en='Head Office - Phnom Penh',
            name_km='ការិយាល័យកណ្តាល - ភ្នំពេញ'
        )
        self.branch_sr = Branch.objects.create(
            code='BR-SR',
            name_en='Siem Reap Branch',
            name_km='សាខាខេត្តសៀមរាប'
        )
        self.admin_user = User.objects.create_user(
            username='admin_boss',
            password='password123',
            role=User.Role.ADMIN,
            is_staff=True
        )
        OfficerProfile.objects.create(
            user=self.admin_user,
            employee_id='ADM-001',
            branch=self.branch_ho,
            department='Executive Management'
        )

        self.officer_user = User.objects.create_user(
            username='officer_sam',
            password='password123',
            role=User.Role.OFFICER
        )
        OfficerProfile.objects.create(
            user=self.officer_user,
            employee_id='OFF-001',
            branch=self.branch_sr,
            department='Credit & Underwriting'
        )

        self.borrower_user = User.objects.create_user(
            username='borrower_bob',
            password='password123',
            role=User.Role.BORROWER
        )
        BorrowerProfile.objects.create(user=self.borrower_user)

    def test_non_admin_cannot_access_staff_creation(self):
        # Borrower
        self.client.login(username='borrower_bob', password='password123')
        resp = self.client.post(reverse('accounts:create_staff'), {'username': 'newbie'})
        self.assertRedirects(resp, reverse('borrower'))

        # Officer
        self.client.login(username='officer_sam', password='password123')
        resp = self.client.post(reverse('accounts:create_staff'), {'username': 'newbie'})
        self.assertRedirects(resp, reverse('officer'))

    def test_admin_can_create_officer_via_ajax(self):
        self.client.login(username='admin_boss', password='password123')
        resp = self.client.post(
            reverse('accounts:create_staff'),
            {
                'username': 'new_officer',
                'first_name': 'Dara',
                'last_name': 'Sok',
                'email': 'dara@bank.com.kh',
                'phone_number': '092111222',
                'role': 'OFFICER',
                'password': 'secretpassword',
                'confirm_password': 'secretpassword',
                'employee_id': 'OFF-009',
                'branch': 'Battambang Branch',
                'department': 'Credit Assessment'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        
        user = User.objects.get(username='new_officer')
        self.assertEqual(user.first_name, 'Dara')
        self.assertEqual(user.role, User.Role.OFFICER)
        self.assertFalse(user.is_staff)
        self.assertEqual(user.officer_profile.employee_id, 'OFF-009')
        self.assertEqual(user.officer_profile.branch.name_en, 'Battambang Branch')

    def test_admin_can_create_admin_staff(self):
        self.client.login(username='admin_boss', password='password123')
        resp = self.client.post(
            reverse('accounts:create_staff'),
            {
                'username': 'second_admin',
                'role': 'ADMIN',
                'password': 'secretpassword',
                'confirm_password': 'secretpassword',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        user = User.objects.get(username='second_admin')
        self.assertTrue(user.is_admin_user)
        self.assertTrue(user.is_staff)

    def test_create_staff_validation_errors(self):
        self.client.login(username='admin_boss', password='password123')
        # Duplicate username
        resp = self.client.post(
            reverse('accounts:create_staff'),
            {
                'username': 'officer_sam',
                'role': 'OFFICER',
                'password': 'password123',
                'confirm_password': 'password123',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

        # Password mismatch
        resp2 = self.client.post(
            reverse('accounts:create_staff'),
            {
                'username': 'officer_new',
                'role': 'OFFICER',
                'password': 'password123',
                'confirm_password': 'differentpassword',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp2.status_code, 400)

    def test_admin_can_edit_staff(self):
        self.client.login(username='admin_boss', password='password123')
        resp = self.client.post(
            reverse('accounts:edit_staff', kwargs={'pk': self.officer_user.pk}),
            {
                'first_name': 'Samuel',
                'last_name': 'King',
                'role': 'ADMIN',
                'branch': 'Head Office',
                'department': 'Risk Management',
                'is_active': 'true'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        self.officer_user.refresh_from_db()
        self.assertEqual(self.officer_user.first_name, 'Samuel')
        self.assertEqual(self.officer_user.role, User.Role.ADMIN)
        self.assertTrue(self.officer_user.is_staff)
        self.assertEqual(self.officer_user.officer_profile.branch.name_en, 'Head Office')

    def test_admin_cannot_demote_or_suspend_self(self):
        self.client.login(username='admin_boss', password='password123')
        resp = self.client.post(
            reverse('accounts:edit_staff', kwargs={'pk': self.admin_user.pk}),
            {
                'role': 'OFFICER',
                'is_active': 'false'
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 400)
        self.admin_user.refresh_from_db()
        self.assertEqual(self.admin_user.role, User.Role.ADMIN)
        self.assertTrue(self.admin_user.is_active)

    def test_admin_toggle_user_status(self):
        self.client.login(username='admin_boss', password='password123')
        resp = self.client.post(
            reverse('accounts:toggle_user_status', kwargs={'pk': self.officer_user.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp.status_code, 200)
        self.officer_user.refresh_from_db()
        self.assertFalse(self.officer_user.is_active)

        # Toggle back
        resp2 = self.client.post(
            reverse('accounts:toggle_user_status', kwargs={'pk': self.officer_user.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp2.status_code, 200)
        self.officer_user.refresh_from_db()
        self.assertTrue(self.officer_user.is_active)

    def test_get_staff_details_api(self):
        self.client.login(username='admin_boss', password='password123')
        resp = self.client.get(reverse('accounts:staff_details', kwargs={'pk': self.officer_user.pk}))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['username'], 'officer_sam')
        self.assertEqual(data['user']['employee_id'], 'OFF-001')

    def test_staff_management_sidebar_and_section_visibility(self):
        # Normal officer does not see staff management
        self.client.login(username='officer_sam', password='password123')
        resp_officer = self.client.get(reverse('officer'))
        self.assertNotContains(resp_officer, 'id="sec-staff"')
        self.assertNotContains(resp_officer, 'data-i18n="nav_staff_management"')

        # Admin user sees staff management
        self.client.login(username='admin_boss', password='password123')
        resp_admin = self.client.get(reverse('officer'))
        self.assertContains(resp_admin, 'id="sec-staff"')
        self.assertContains(resp_admin, 'data-i18n="nav_staff_management"')
        self.assertContains(resp_admin, 'id="createStaffModal"')
        self.assertContains(resp_admin, 'id="editStaffModal"')
