from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.utils.translation import gettext_lazy as _


class CustomPasswordResetForm(PasswordResetForm):

    email = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email"
            }
        )
    )

    def clean_email(self):

        email = self.cleaned_data["email"]

        UserModel = get_user_model()

        exists = UserModel.objects.filter(
            email__iexact=email,
            is_active=True
        ).exists()

        if not exists:

            raise forms.ValidationError(
                _("No active account exists with this email address.")
            )

        return email