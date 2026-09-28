import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from AdminApp.models import (
    VendorDetails,
    Product,
    SellerProductEnquiry,
    LotBatchEnquiry,
    Lot,
    VendorOTP,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Deduplicates registered users (VendorDetails) by email. "
        "Consolidates duplicate accounts into a single canonical user and reassigns "
        "all associated products, enquiries, lots, and OTPs to the retained vendor ID so no vendor association is lost."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate deduplication without modifying database records.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("=== RUNNING IN DRY RUN MODE ==="))
        else:
            self.stdout.write(self.style.SUCCESS("=== RUNNING DEDUPLICATION ==="))

        vendors = VendorDetails.objects.all().order_by("id")
        email_groups = {}
        for v in vendors:
            email_clean = (v.email or "").strip().lower()
            if email_clean:
                email_groups.setdefault(email_clean, []).append(v)

        duplicate_email_groups = {
            email: v_list for email, v_list in email_groups.items() if len(v_list) > 1
        }

        self.stdout.write(f"Total registered users analyzed: {vendors.count()}")
        self.stdout.write(f"Unique email accounts: {len(email_groups)}")
        self.stdout.write(f"Duplicate email groups found: {len(duplicate_email_groups)}")

        total_reassigned_products = 0
        total_reassigned_enquiries = 0
        total_reassigned_lots = 0
        total_users_removed = 0

        with transaction.atomic():
            for email, v_list in duplicate_email_groups.items():
                self.stdout.write(self.style.NOTICE(f"\nProcessing duplicate group for email: '{email}' ({len(v_list)} accounts)"))

                # Rank vendors to choose the best primary vendor to retain
                # Criteria:
                # 1. Has password set (pass_word is present and non-empty)
                # 2. Account active (status is True)
                # 3. Has associated products
                # 4. Oldest created_at / lowest ID
                def vendor_rank(v):
                    has_pass = 1 if v.pass_word and len(v.pass_word.strip()) > 0 else 0
                    is_active = 1 if v.status else 0
                    p_count = Product.objects.filter(vendor=v).count()
                    # Negate ID so earlier ID scores higher
                    return (has_pass, is_active, p_count, -v.id)

                sorted_vendors = sorted(v_list, key=vendor_rank, reverse=True)
                primary_vendor = sorted_vendors[0]
                duplicate_vendors = sorted_vendors[1:]

                self.stdout.write(
                    f"  -> Retaining Primary User ID: {primary_vendor.id} (Username: '{primary_vendor.username}')"
                )

                for dup in duplicate_vendors:
                    self.stdout.write(
                        f"  -> Merging Duplicate User ID: {dup.id} (Username: '{dup.username}') into Primary User ID: {primary_vendor.id}"
                    )

                    # Reassign products
                    prods_to_reassign = Product.objects.filter(vendor=dup)
                    p_count = prods_to_reassign.count()
                    if p_count > 0:
                        self.stdout.write(f"     Reassigning {p_count} Products from vendor {dup.id} -> {primary_vendor.id}")
                        if not dry_run:
                            prods_to_reassign.update(vendor=primary_vendor)
                        total_reassigned_products += p_count

                    # Reassign SellerProductEnquiries
                    spe_to_reassign = SellerProductEnquiry.objects.filter(vendor=dup)
                    spe_count = spe_to_reassign.count()
                    if spe_count > 0:
                        self.stdout.write(f"     Reassigning {spe_count} Seller Enquiries from vendor {dup.id} -> {primary_vendor.id}")
                        if not dry_run:
                            spe_to_reassign.update(vendor=primary_vendor)
                        total_reassigned_enquiries += spe_count

                    # Reassign LotBatchEnquiries
                    lbe_to_reassign = LotBatchEnquiry.objects.filter(uploaded_by=dup)
                    lbe_count = lbe_to_reassign.count()
                    if lbe_count > 0:
                        self.stdout.write(f"     Reassigning {lbe_count} Lot Batch Enquiries from vendor {dup.id} -> {primary_vendor.id}")
                        if not dry_run:
                            lbe_to_reassign.update(uploaded_by=primary_vendor)
                        total_reassigned_lots += lbe_count

                    # Reassign Lots
                    lots_to_reassign = Lot.objects.filter(vendor=dup)
                    lot_count = lots_to_reassign.count()
                    if lot_count > 0:
                        self.stdout.write(f"     Reassigning {lot_count} Lots from vendor {dup.id} -> {primary_vendor.id}")
                        if not dry_run:
                            lots_to_reassign.update(vendor=primary_vendor)
                        total_reassigned_lots += lot_count

                    # Reassign VendorOTPs
                    otps_to_reassign = VendorOTP.objects.filter(vendor=dup)
                    if otps_to_reassign.exists():
                        if not dry_run:
                            otps_to_reassign.update(vendor=primary_vendor)

                    # Delete duplicate vendor
                    if not dry_run:
                        dup.delete()
                    total_users_removed += 1

                # Clean email formatting on primary vendor
                if not dry_run:
                    primary_vendor.email = email
                    primary_vendor.save(update_fields=["email"])

            # Also check for unassigned products (vendor is NULL) that match vendor email in raw_data/excel
            unassigned_products = Product.objects.filter(vendor__isnull=True)
            if unassigned_products.exists():
                self.stdout.write(self.style.NOTICE(f"\nChecking {unassigned_products.count()} unassigned product(s)..."))
                for p in unassigned_products:
                    # Check if email can be determined from raw_data or active data
                    raw_email = (p.raw_data.get("email") if isinstance(p.raw_data, dict) else None) or ""
                    clean_raw_email = raw_email.strip().lower()
                    if clean_raw_email and clean_raw_email in email_groups:
                        matched_vendor = VendorDetails.objects.filter(email__iexact=clean_raw_email).first()
                        if matched_vendor:
                            self.stdout.write(f"  -> Assigning Product '{p.product_id}' to Vendor ID: {matched_vendor.id} ({matched_vendor.email})")
                            if not dry_run:
                                p.vendor = matched_vendor
                                p.save(update_fields=["vendor"])
                            total_reassigned_products += 1

            if dry_run:
                self.stdout.write(self.style.WARNING("\nDry run complete. No database changes were made."))
                # Rollback transaction in dry-run mode
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("\n=== SUMMARY ==="))
        self.stdout.write(f"Duplicate email groups processed: {len(duplicate_email_groups)}")
        self.stdout.write(f"Duplicate users removed: {total_users_removed}")
        self.stdout.write(f"Products reassigned/updated: {total_reassigned_products}")
        self.stdout.write(f"Seller enquiries reassigned: {total_reassigned_enquiries}")
        self.stdout.write(f"Lot enquiries reassigned: {total_reassigned_lots}")
