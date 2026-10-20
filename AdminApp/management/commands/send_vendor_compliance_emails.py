import time
import logging
from django.core.management.base import BaseCommand
from AdminApp.models import VendorDetails, Product
from AdminApp.services import EmailService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Send email notifications to vendors with incomplete profiles (to complete their profile) "
        "and vendors with incomplete product specifications (to fill missing details)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            choices=["profile", "products", "all"],
            default="all",
            help="Type of notification to send: 'profile' (profile reminder), 'products' (product specs missing), or 'all'",
        )
        parser.add_argument(
            "--email",
            type=str,
            default=None,
            help="Target a specific vendor email address (useful for testing)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate and print recipient list and email contents without actually dispatching emails",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of vendors to process",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.4,
            help="Delay in seconds between email dispatches to prevent rate-limiting (default 0.4s)",
        )

    def handle(self, *args, **options):
        notification_type = options["type"]
        target_email = options["email"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        delay = options["delay"]

        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE(f" SURPLUS MARKET VENDOR COMPLIANCE EMAIL DISPATCHER"))
        self.stdout.write(self.style.NOTICE(f" Type: {notification_type.upper()} | Dry-run: {dry_run} | Target: {target_email or 'All Eligible Vendors'}"))
        self.stdout.write(self.style.NOTICE("=" * 70))

        vendors_qs = VendorDetails.objects.all().order_by("id")
        if target_email:
            vendors_qs = vendors_qs.filter(email__iexact=target_email.strip())

        # Exclude non-routable/offline test domains
        vendors = [v for v in vendors_qs if v.email and "@" in v.email and not v.email.endswith(".local")]

        if limit:
            vendors = vendors[:limit]

        self.stdout.write(f"Found {len(vendors)} vendor accounts to evaluate.\n")

        profile_sent = 0
        profile_skipped = 0
        product_sent = 0
        product_skipped = 0

        for idx, vendor in enumerate(vendors, start=1):
            vendor_name = vendor.full_name or vendor.company_name or vendor.username
            email = vendor.email.strip()
            details = vendor.get_profile_completion_details()
            is_complete = details.get("is_complete", False)
            percentage = details.get("percentage", 0)
            missing_labels = details.get("missing_fields_labels", [])

            self.stdout.write(f"[{idx}/{len(vendors)}] Evaluating: {vendor_name} ({email}) - Profile: {percentage}%")

            # -------------------------------------------------------------
            # 1. Profile Incomplete Reminder
            # -------------------------------------------------------------
            if notification_type in ["profile", "all"]:
                if not is_complete:
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f"   -> [DRY-RUN] Would send PROFILE REMINDER ({percentage}% complete, Missing: {', '.join(missing_labels)})"
                            )
                        )
                        profile_sent += 1
                    else:
                        try:
                            ok = EmailService.send_profile_completion_reminder_email(vendor)
                            if ok:
                                profile_sent += 1
                                self.stdout.write(self.style.SUCCESS(f"   [OK] Profile completion reminder sent ({percentage}%)"))
                            else:
                                profile_skipped += 1
                                self.stdout.write(self.style.ERROR(f"   [FAILED] Failed to send profile reminder email."))
                        except Exception as e:
                            profile_skipped += 1
                            self.stdout.write(self.style.ERROR(f"   [FAILED] Error sending profile reminder: {e}"))

                        if delay > 0:
                            time.sleep(delay)
                else:
                    profile_skipped += 1
                    self.stdout.write(f"   - Profile is 100% complete. Skipped profile reminder.")

            # -------------------------------------------------------------
            # 2. Product Information Incomplete Notice
            # -------------------------------------------------------------
            if notification_type in ["products", "all"]:
                vendor_products = Product.objects.filter(vendor=vendor)
                total_prods = vendor_products.count()

                incomplete_items = []
                for p in vendor_products:
                    missing_specs = []
                    if not p.brand_name:
                        missing_specs.append("Brand Name")
                    if not p.model_no:
                        missing_specs.append("Model Number")
                    if not p.dimensions:
                        missing_specs.append("Dimensions")
                    if not p.manufacturing_country:
                        missing_specs.append("Origin Country")
                    if not p.description:
                        missing_specs.append("Detailed Description")

                    if missing_specs:
                        incomplete_items.append({
                            "product_id": p.product_id,
                            "product_name": p.product_name,
                            "missing_fields": missing_specs,
                        })

                if incomplete_items:
                    if dry_run:
                        self.stdout.write(
                            self.style.WARNING(
                                f"   -> [DRY-RUN] Would send PRODUCT INFO INCOMPLETE ({len(incomplete_items)}/{total_prods} products require specs)"
                            )
                        )
                        product_sent += 1
                    else:
                        try:
                            ok = EmailService.send_product_info_incomplete_email(
                                vendor=vendor,
                                incomplete_products=incomplete_items,
                                total_count=total_prods
                            )
                            if ok:
                                product_sent += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"   [OK] Product incomplete notice sent ({len(incomplete_items)} listings missing specs)"
                                    )
                                )
                            else:
                                product_skipped += 1
                                self.stdout.write(self.style.ERROR(f"   [FAILED] Failed to send product info email."))
                        except Exception as e:
                            product_skipped += 1
                            self.stdout.write(self.style.ERROR(f"   [FAILED] Error sending product info notice: {e}"))

                        if delay > 0:
                            time.sleep(delay)
                else:
                    product_skipped += 1
                    if total_prods > 0:
                        self.stdout.write(f"   - All {total_prods} products have complete specifications. Skipped product notice.")
                    else:
                        self.stdout.write(f"   - No products associated with this vendor. Skipped product notice.")

            self.stdout.write("")

        self.stdout.write(self.style.NOTICE("=" * 70))
        self.stdout.write(self.style.NOTICE(" SUMMARY OF EMAIL DISPATCH"))
        self.stdout.write(self.style.NOTICE("=" * 70))
        if notification_type in ["profile", "all"]:
            self.stdout.write(f"Profile Completion Reminders Sent: {profile_sent} | Skipped/Failed: {profile_skipped}")
        if notification_type in ["products", "all"]:
            self.stdout.write(f"Product Incomplete Notices Sent:   {product_sent} | Skipped/Failed: {product_skipped}")
        self.stdout.write(self.style.SUCCESS(f"Total Emails Handled: {profile_sent + product_sent}"))
        self.stdout.write(self.style.NOTICE("=" * 70))
