"""
Password Policy Definition and Enforcement for Admin Accounts.

Enforces the latest modern security standard:
- Minimum 8 characters
- At least 1 uppercase letter (A-Z)
- At least 1 lowercase letter (a-z)
- At least 1 numeric digit (0-9)
- At least 1 special character (!@#$%^&* etc.)
- Django built-in password validators (common password lists, attribute similarity)
"""
import re
from typing import List, Optional
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password as django_validate_password
from rest_framework import serializers

PASSWORD_MIN_LENGTH = 8
SPECIAL_CHARS_PATTERN = r'[!@#$%^&*(),.?":{}|<>\-_+=\[\]\\\/~`\';]'


def validate_admin_password(password: str, user=None) -> List[str]:
    """
    Validates a password against the latest password policy.
    Returns a list of human-readable error messages if any requirement is violated.
    Returns an empty list if the password is valid.
    """
    errors: List[str] = []
    if not password:
        return ["Password is required."]

    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter (A-Z).")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter (a-z).")

    if not re.search(r"[0-9]", password):
        errors.append("Password must contain at least one numeric digit (0-9).")

    if not re.search(SPECIAL_CHARS_PATTERN, password):
        errors.append("Password must contain at least one special character (e.g. !@#$%^&*).")

    # Django built-in validators (MinimumLengthValidator, CommonPasswordValidator, etc.)
    try:
        django_validate_password(password, user=user)
    except DjangoValidationError as exc:
        for msg in exc.messages:
            if msg not in errors:
                errors.append(msg)

    return errors


def enforce_admin_password_policy(password: str, user=None, field_name: str = "password"):
    """
    Helper function for DRF serializers and forms.
    Raises serializers.ValidationError if any policy rules are violated.
    """
    errors = validate_admin_password(password, user=user)
    if errors:
        # Return either a single joined string or list based on caller expectations
        raise serializers.ValidationError({field_name: " ".join(errors)})
