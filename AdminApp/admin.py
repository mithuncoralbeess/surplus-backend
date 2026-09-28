from django import forms
from django.contrib import admin
from .models import AdminDetails, AdminPasswordResetOTP


class AdminDetailsForm(forms.ModelForm):
    raw_password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        required=False,
        help_text="Enter a new raw password to set or update. Leave blank to keep existing password."
    )

    class Meta:
        model = AdminDetails
        fields = [
            "username",
            "email",
            "raw_password",
            "account_type",
            "status",
            "session_version",
            "web_is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["raw_password"].required = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        raw_password = self.cleaned_data.get("raw_password")
        if raw_password:
            instance.set_password(raw_password)
        if commit:
            instance.save()
        return instance


@admin.register(AdminDetails)
class AdminDetailsAdmin(admin.ModelAdmin):
    form = AdminDetailsForm
    list_display = (
        "id",
        "username",
        "email",
        "account_type",
        "status",
        "session_version",
        "web_is_active",
        "created_at",
    )
    list_filter = ("account_type", "status", "web_is_active", "created_at")
    search_fields = ("username", "email")
    readonly_fields = ("session_version", "created_at", "updated_at")


@admin.register(AdminPasswordResetOTP)
class AdminPasswordResetOTPAdmin(admin.ModelAdmin):
    list_display = ("id", "admin", "email", "otp", "is_used", "created_at")
    list_filter = ("is_used", "created_at")
    search_fields = ("email", "otp", "admin__username")

from .models import VendorDetails
admin.site.register(VendorDetails)
