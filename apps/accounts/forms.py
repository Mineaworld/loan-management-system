from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from .models import User, BorrowerProfile


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'loginUsername', 'placeholder': 'officer1 or borrower1'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'id': 'loginPassword', 'placeholder': '••••••••'})
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                user_by_phone = User.objects.filter(phone_number=username).first()
                if user_by_phone and user_by_phone.check_password(password):
                    self.user_cache = user_by_phone

            if self.user_cache is None:
                raise forms.ValidationError('ឈ្មោះអ្នកប្រើ ឬលេខសម្ងាត់មិនត្រឹមត្រូវ / Invalid username or password.')
            elif not self.user_cache.is_active:
                raise forms.ValidationError('គណនីនេះត្រូវបានផ្អាក / Account is inactive.')

        return self.cleaned_data


class BorrowerRegistrationForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150, required=True)
    phone_number = forms.CharField(max_length=30, required=True)
    national_id = forms.CharField(max_length=50, required=True)
    primary_currency = forms.ChoiceField(choices=[('USD', 'USD'), ('KHR', 'KHR')], initial='USD')
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=True)

    class Meta:
        model = User
        fields = ('phone_number', 'national_id', 'primary_currency')

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()
        if User.objects.filter(phone_number=phone).exists():
            raise forms.ValidationError('លេខទូរស័ព្ទនេះត្រូវបានប្រើប្រាស់រួចហើយ / Phone number already registered.')
        return phone

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('confirm_password')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_password', 'លេខសម្ងាត់ទាំងពីរមិនត្រូវគ្នា / Passwords do not match.')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.BORROWER

        full_name = self.cleaned_data.get('full_name', '').strip()
        names = full_name.split(' ', 1)
        user.first_name = names[0]
        user.last_name = names[1] if len(names) > 1 else ''

        phone = self.cleaned_data.get('phone_number', '').replace(' ', '').replace('-', '')
        base_username = f"user_{phone}" if phone else "user"
        candidate_username = base_username
        suffix = 1
        while User.objects.filter(username=candidate_username).exists():
            candidate_username = f"{base_username}_{suffix}"
            suffix += 1
        user.username = candidate_username
        user.set_password(self.cleaned_data['password'])

        if commit:
            user.save()
            BorrowerProfile.objects.get_or_create(user=user)
        return user
