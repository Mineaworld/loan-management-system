from django import forms
from .models import LoanApplication, LoanProduct


class LoanApplicationForm(forms.ModelForm):
    class Meta:
        model = LoanApplication
        fields = ('product', 'amount', 'currency', 'tenure_months', 'monthly_income', 'purpose')
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'applyProduct'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm font-monospace', 'id': 'applyAmount'}),
            'currency': forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'applyCurrency'}),
            'tenure_months': forms.NumberInput(attrs={'class': 'form-control form-control-sm font-monospace', 'id': 'applyTenure'}),
            'monthly_income': forms.NumberInput(attrs={'class': 'form-control form-control-sm font-monospace', 'id': 'applyIncome'}),
            'purpose': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'id': 'applyPurpose'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        amount = cleaned_data.get('amount')
        tenure_months = cleaned_data.get('tenure_months')
        monthly_income = cleaned_data.get('monthly_income')

        if product and amount:
            if amount < product.min_amount:
                self.add_error('amount', f"ចំនួនទឹកប្រាក់ត្រូវតែចាប់ពី {product.min_amount} {product.currency} ឡើងទៅ / Minimum amount is {product.min_amount}.")
            elif amount > product.max_amount:
                self.add_error('amount', f"ចំនួនទឹកប្រាក់មិនអាចលើសពី {product.max_amount} {product.currency} / Maximum amount is {product.max_amount}.")

        if product and tenure_months:
            if tenure_months < product.min_tenure_months:
                self.add_error('tenure_months', f"រយៈពេលតិចបំផុតគឺ {product.min_tenure_months} ខែ / Minimum tenure is {product.min_tenure_months} months.")
            elif tenure_months > product.max_tenure_months:
                self.add_error('tenure_months', f"រយៈពេលច្រើនបំផុតគឺ {product.max_tenure_months} ខែ / Maximum tenure is {product.max_tenure_months} months.")

        if monthly_income and monthly_income <= 0:
            self.add_error('monthly_income', 'ប្រាក់ចំណូលត្រូវតែធំជាង 0 / Monthly income must be greater than zero.')

        return cleaned_data

    def save(self, borrower, commit=True):
        application = super().save(commit=False)
        application.borrower = borrower
        if commit:
            application.save()
        return application
