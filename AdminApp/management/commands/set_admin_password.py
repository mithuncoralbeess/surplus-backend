"""
Set (reset) an AdminDetails password using Django's PBKDF2 hasher.

Usage:
    python manage.py set_admin_password super@gmail.com
    python manage.py set_admin_password super@gmail.com --password "SuperAdmin@2026!"

Also reports any admins whose stored password is not yet a Django hash.
"""
import getpass

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from AdminApp.models import AdminDetails

DJANGO_HASH_PREFIXES = ("pbkdf2_", "argon2", "bcrypt")


class Command(BaseCommand):
    help = "Set an admin's password (stored as a Django PBKDF2 hash) and invalidate their sessions."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Admin email address")
        parser.add_argument(
            "--password",
            help="New password. If omitted you will be prompted securely.",
        )
        parser.add_argument(
            "--no-policy-check",
            action="store_true",
            help="Bypass password policy check.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        try:
            admin = AdminDetails.objects.get(email__iexact=email)
        except AdminDetails.DoesNotExist:
            raise CommandError(f"No admin found with email '{email}'.")

        password = options.get("password")
        if not password:
            password = getpass.getpass("New password: ")
            if password != getpass.getpass("Confirm password: "):
                raise CommandError("Passwords do not match.")
        if not password:
            raise CommandError("Password cannot be empty.")

        if not options.get("no_policy_check"):
            from AdminApp.password_policy import validate_admin_password
            policy_errors = validate_admin_password(password)
            if policy_errors:
                raise CommandError(
                    "Password does not satisfy the latest password policy:\n - "
                    + "\n - ".join(policy_errors)
                )

        admin.set_password(password)
        admin.session_version += 1  # force logout of existing sessions
        admin.save(update_fields=["pass_word", "session_version", "updated_at"])

        # Also sync corresponding Django User (auth_user) records
        try:
            from django.contrib.auth.models import User
            django_users = (
                User.objects.filter(email__iexact=admin.email)
                | User.objects.filter(username__iexact=admin.username)
            ).distinct()
            for du in django_users:
                du.set_password(password)
                du.save()
            if django_users.exists():
                self.stdout.write(self.style.SUCCESS(
                    f"Synced {django_users.count()} matching Django auth_user record(s)."
                ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not sync auth_user: {exc}"))

        cache.delete(f"admin_obj_{admin.id}")
        cache.set(f"admin_version_{admin.id}", admin.session_version, timeout=86400)

        self.stdout.write(self.style.SUCCESS(f"Password updated (hashed) for {admin.email}."))

        legacy = [
            a.email
            for a in AdminDetails.objects.all()
            if not (a.pass_word or "").startswith(DJANGO_HASH_PREFIXES)
        ]
        if legacy:
            self.stdout.write(self.style.WARNING(
                "Admins still on legacy SHA-256 hashes (auto-upgraded to PBKDF2 on next login): "
                + ", ".join(legacy)
            ))
