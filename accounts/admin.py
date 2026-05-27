from django import forms
from django.contrib import admin

from .models import User, Department, Role


class UserAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = "__all__"

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            raise forms.ValidationError("Email is required.")
        return email


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ("username", "full_name", "email", "employee_id", "department", "role", "can_manage_stock", "is_active")
    search_fields = ("username", "full_name", "email")
    list_filter = ("department", "role", "can_manage_stock", "is_active")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")