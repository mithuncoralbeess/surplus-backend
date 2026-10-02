from django import forms
from django.contrib import admin
from .models import AdminDetails, AdminPasswordResetOTP, VendorDetails, ProductImage


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


admin.site.register(VendorDetails)


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "is_real_photo", "image_url", "uploaded_at")
    list_filter = ("is_real_photo", "uploaded_at")
    search_fields = ("product__product_name", "product__product_id", "image_url")


from .models import VendorNotification

@admin.register(VendorNotification)
class VendorNotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "vendor", "notification_type", "title", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = (
        "title",
        "message",
        "vendor__vendor_id",
        "vendor__username",
        "vendor__email",
        "vendor__full_name",
    )
    readonly_fields = ("created_at",)
    actions = ["mark_as_read"]

    @admin.action(description="Mark selected notifications as read")
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notification(s) marked as read.")

