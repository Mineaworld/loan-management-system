from functools import wraps
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.db.models import Q
from .forms import LoginForm, BorrowerRegistrationForm
from .models import User, OfficerProfile, Branch


def resolve_branch(branch_input):
    if not branch_input:
        return Branch.objects.filter(code='HO-PP').first() or Branch.objects.first()
    if isinstance(branch_input, Branch):
        return branch_input
    branch_str = str(branch_input).strip()
    if not branch_str:
        return Branch.objects.filter(code='HO-PP').first() or Branch.objects.first()

    branch_obj = Branch.objects.filter(
        Q(code__iexact=branch_str) | Q(name_en__iexact=branch_str) | Q(name_km__iexact=branch_str)
    ).first()
    if not branch_obj and branch_str.isdigit():
        branch_obj = Branch.objects.filter(pk=int(branch_str)).first()
    if not branch_obj and branch_str:
        code = branch_str[:10].upper().replace(' ', '-')
        branch_obj, _ = Branch.objects.get_or_create(
            name_en=branch_str,
            defaults={'code': code, 'name_km': branch_str}
        )
    if not branch_obj:
        branch_obj = Branch.objects.filter(code='HO-PP').first() or Branch.objects.first()
    return branch_obj


def role_redirect(user):
    if user.is_officer or user.is_admin_user:
        return redirect('officer')
    return redirect('borrower')


def role_redirect_view(request):
    if not request.user.is_authenticated:
        return redirect('accounts:auth')
    return role_redirect(request.user)


def borrower_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'សូមចូលប្រើប្រាស់គណនីជាមុនសិន / Please sign in to continue.')
            return redirect('accounts:auth')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def officer_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'សូមចូលប្រើប្រាស់គណនីជាមុនសិន / Please sign in to continue.')
            return redirect('accounts:auth')
        if not (request.user.is_officer or request.user.is_admin_user):
            messages.error(request, 'អ្នកមិនមានសិទ្ធិចូលមើលទំព័រនេះទេ / You do not have permission to view the officer portal.')
            return redirect('borrower')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, 'សូមចូលប្រើប្រាស់គណនីជាមុនសិន / Please sign in to continue.')
            return redirect('accounts:auth')
        if not request.user.is_admin_user:
            messages.error(request, 'អ្នកមិនមានសិទ្ធិជាអ្នកគ្រប់គ្រងប្រព័ន្ធឡើយ / Administrator access required.')
            if request.user.is_borrower:
                return redirect('borrower')
            return redirect('officer')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


class UnifiedAuthView(View):
    template_name = 'accounts/auth.html'

    def get(self, request):
        if request.user.is_authenticated:
            return role_redirect(request.user)
        login_form = LoginForm()
        reg_form = BorrowerRegistrationForm()
        return render(request, self.template_name, {
            'login_form': login_form,
            'reg_form': reg_form,
            'active_tab': 'LOGIN',
        })

    def post(self, request):
        action = request.POST.get('auth_action', 'LOGIN')

        if action == 'LOGIN':
            login_form = LoginForm(request, data=request.POST)
            reg_form = BorrowerRegistrationForm()
            if login_form.is_valid():
                user = login_form.get_user()
                login(request, user)
                messages.success(request, f"ស្វាគមន៍មកកាន់ប្រព័ន្ធ, {user.get_full_name() or user.username}!")
                return role_redirect(user)
            else:
                for error_list in login_form.errors.values():
                    for err in error_list:
                        messages.error(request, err)
                return render(request, self.template_name, {
                    'login_form': login_form,
                    'reg_form': reg_form,
                    'active_tab': 'LOGIN',
                })

        elif action == 'REGISTER':
            reg_form = BorrowerRegistrationForm(request.POST)
            login_form = LoginForm()
            if reg_form.is_valid():
                user = reg_form.save()
                login(request, user)
                messages.success(request, 'បង្កើតគណនីបានជោគជ័យ! សូមស្វាគមន៍ / Account created successfully!')
                return redirect('borrower')
            else:
                for field, error_list in reg_form.errors.items():
                    for err in error_list:
                        messages.error(request, f"{err}")
                return render(request, self.template_name, {
                    'login_form': login_form,
                    'reg_form': reg_form,
                    'active_tab': 'REGISTER',
                })

        return redirect('accounts:auth')


def logout_view(request):
    logout(request)
    messages.info(request, 'លោកអ្នកបានចាកចេញដោយជោគជ័យ / Successfully logged out.')
    return redirect('accounts:auth')


@login_required
@admin_required
def create_staff_view(request):
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    username = request.POST.get('username', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()
    role = request.POST.get('role', User.Role.OFFICER).strip().upper()
    password = request.POST.get('password', '')
    confirm_password = request.POST.get('confirm_password', '')
    employee_id = request.POST.get('employee_id', '').strip()
    branch = request.POST.get('branch', 'Head Office - Phnom Penh').strip()
    department = request.POST.get('department', 'Credit & Underwriting').strip()

    errors = []
    if not username:
        errors.append('សូមបញ្ចូលឈ្មោះគណនី (Username) / Username is required.')
    elif User.objects.filter(username__iexact=username).exists():
        errors.append('ឈ្មោះគណនីនេះត្រូវបានប្រើប្រាស់រួចហើយ / Username is already taken.')

    if role not in [User.Role.OFFICER, User.Role.ADMIN]:
        errors.append('តួនាទីមិនត្រឹមត្រូវ / Invalid staff role selected.')

    if not password:
        errors.append('សូមបញ្ចូលពាក្យសម្ងាត់ / Password is required.')
    elif len(password) < 6:
        errors.append('ពាក្យសម្ងាត់ត្រូវមានយ៉ាងតិច ៦ តួអក្សរ / Password must be at least 6 characters.')
    elif password != confirm_password:
        errors.append('ពាក្យសម្ងាត់ទាំងពីរមិនដូចគ្នាទេ / Passwords do not match.')

    if phone_number and User.objects.filter(phone_number=phone_number).exists():
        errors.append('លេខទូរស័ព្ទនេះត្រូវបានចុះឈ្មោះរួចហើយ / Phone number is already registered.')

    if errors:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': errors, 'error': errors[0]}, status=400)
        for err in errors:
            messages.error(request, err)
        return redirect('loans:officer_dashboard')

    with transaction.atomic():
        new_staff = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            phone_number=phone_number,
            is_staff=(role == User.Role.ADMIN),
        )
        emp_code = employee_id or f"EMP-{new_staff.id:04d}"
        branch_obj = resolve_branch(branch)
        OfficerProfile.objects.create(
            user=new_staff,
            employee_id=emp_code,
            branch=branch_obj,
            department=department or ('Administration & Management' if role == User.Role.ADMIN else 'Credit & Underwriting'),
            phone=phone_number
        )

    success_msg = f"បានបង្កើតគណនី {new_staff.get_role_display()} ({new_staff.username}) ជោគជ័យ! / Created {new_staff.get_role_display()} ({new_staff.username}) successfully!"
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': success_msg,
            'user': {
                'id': new_staff.id,
                'username': new_staff.username,
                'full_name': new_staff.get_full_name() or new_staff.username,
                'role': new_staff.role,
                'role_display': new_staff.get_role_display(),
                'employee_id': emp_code,
                'branch': branch_obj.name_en if branch_obj else branch,
                'department': department,
            }
        })

    messages.success(request, success_msg)
    return redirect('loans:officer_dashboard')


@login_required
@admin_required
def edit_staff_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()
    role = request.POST.get('role', target_user.role).strip().upper()
    branch = request.POST.get('branch', '').strip()
    department = request.POST.get('department', '').strip()
    employee_id = request.POST.get('employee_id', '').strip()
    new_password = request.POST.get('new_password', '').strip()
    is_active_val = request.POST.get('is_active')

    errors = []
    if role not in [User.Role.ADMIN, User.Role.OFFICER, User.Role.BORROWER]:
        errors.append('តួនាទីមិនត្រឹមត្រូវ / Invalid role selected.')

    if target_user == request.user:
        if role != User.Role.ADMIN:
            errors.append('អ្នកមិនអាចបន្ថយតួនាទីគណនីផ្ទាល់ខ្លួនបានទេ / You cannot demote your own administrator account.')
        if is_active_val is not None and is_active_val not in ['true', 'on', '1', True]:
            errors.append('អ្នកមិនអាចផ្អាកគណនីផ្ទាល់ខ្លួនបានទេ / You cannot deactivate your own account.')

    if new_password and len(new_password) < 6:
        errors.append('ពាក្យសម្ងាត់ថ្មីត្រូវមានយ៉ាងតិច ៦ តួអក្សរ / New password must be at least 6 characters.')

    if phone_number and User.objects.filter(phone_number=phone_number).exclude(pk=target_user.pk).exists():
        errors.append('លេខទូរស័ព្ទនេះត្រូវបានចុះឈ្មោះដោយគណនីផ្សេងរួចហើយ / Phone number is used by another account.')

    if errors:
        if is_ajax:
            return JsonResponse({'success': False, 'errors': errors, 'error': errors[0]}, status=400)
        for err in errors:
            messages.error(request, err)
        return redirect('loans:officer_dashboard')

    with transaction.atomic():
        target_user.first_name = first_name
        target_user.last_name = last_name
        target_user.email = email
        target_user.phone_number = phone_number
        target_user.role = role
        target_user.is_staff = (role == User.Role.ADMIN)

        if is_active_val is not None and target_user != request.user:
            target_user.is_active = is_active_val in ['true', 'on', '1', True]

        if new_password:
            target_user.set_password(new_password)

        target_user.save()

        if role in [User.Role.OFFICER, User.Role.ADMIN]:
            profile, _ = OfficerProfile.objects.get_or_create(user=target_user)
            if branch:
                profile.branch = resolve_branch(branch)
            if department:
                profile.department = department
            if employee_id:
                profile.employee_id = employee_id
            profile.phone = phone_number
            profile.save()

    success_msg = f"បានកែប្រែព័ត៌មានគណនី {target_user.username} ជោគជ័យ! / Updated account {target_user.username} successfully!"
    if is_ajax:
        return JsonResponse({'success': True, 'message': success_msg})

    messages.success(request, success_msg)
    return redirect('loans:officer_dashboard')


@login_required
@admin_required
def toggle_user_status_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)

    if target_user == request.user:
        return JsonResponse({
            'success': False,
            'error': 'អ្នកមិនអាចផ្អាកគណនីផ្ទាល់ខ្លួនរបស់អ្នកបានឡើយ / You cannot deactivate your own account.'
        }, status=400)

    target_user.is_active = not target_user.is_active
    target_user.save()

    status_kh = 'សកម្ម' if target_user.is_active else 'ត្រូវបានផ្អាក'
    status_en = 'Active' if target_user.is_active else 'Suspended'
    msg = f"គណនី {target_user.username} ឥឡូវនេះស្ថិតក្នុងស្ថានភាព {status_kh} / Account {target_user.username} is now {status_en}."

    return JsonResponse({
        'success': True,
        'is_active': target_user.is_active,
        'message': msg
    })


@login_required
@admin_required
def get_user_details_api(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    profile = getattr(target_user, 'officer_profile', None)

    return JsonResponse({
        'success': True,
        'user': {
            'id': target_user.id,
            'username': target_user.username,
            'first_name': target_user.first_name,
            'last_name': target_user.last_name,
            'full_name': target_user.get_full_name() or target_user.username,
            'email': target_user.email,
            'phone_number': target_user.phone_number or '',
            'role': target_user.role,
            'role_display': target_user.get_role_display(),
            'is_active': target_user.is_active,
            'employee_id': profile.employee_id if profile else '',
            'branch': profile.branch.name_en if (profile and profile.branch) else 'Head Office - Phnom Penh',
            'branch_code': profile.branch.code if (profile and profile.branch) else 'HO-PP',
            'department': profile.department if profile else 'Credit & Underwriting',
            'date_joined': target_user.date_joined.strftime('%Y-%m-%d %H:%M') if target_user.date_joined else '',
        }
    })
