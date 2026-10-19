import os
import re
import openpyxl
from django.core.management.base import BaseCommand
from AdminApp.models import VendorDetails


def detect_country(phone: str, email: str, company: str, default="United Arab Emirates") -> str:
    raw_phone = str(phone or "").strip()
    clean_p = re.sub(r"[^\d+]", "", raw_phone)
    lower_email = str(email or "").lower()
    lower_comp = str(company or "").lower()

    if clean_p.startswith("+86") or clean_p.startswith("86"):
        return "China"
    if clean_p.startswith("+82") or clean_p.startswith("82"):
        return "South Korea"
    if clean_p.startswith("+886"):
        return "Taiwan"
    if clean_p.startswith("+966") or clean_p.startswith("966"):
        return "Saudi Arabia"
    if clean_p.startswith("+44") or clean_p.startswith("44"):
        return "United Kingdom"
    if clean_p.startswith("+55"):
        return "Brazil"
    if clean_p.startswith("+20") or clean_p.startswith("0201"):
        return "Egypt"
    if clean_p.startswith("+971") or clean_p.startswith("00971") or clean_p.startswith("971") or (clean_p.startswith("05") and len(clean_p) == 10):
        return "United Arab Emirates"
    if clean_p.startswith("+974") or (clean_p.isdigit() and len(clean_p) == 8 and clean_p[0] in ["3", "5", "6", "7"]):
        return "Qatar"
    if lower_email.endswith(".nz") or clean_p.startswith("021"):
        return "New Zealand"
    if lower_email.endswith(".nl") or "amsterdam" in lower_email or "amsterdam" in lower_comp:
        return "Netherlands"
    if clean_p.startswith("9620") or clean_p.startswith("968"):
        return "Oman"
    if clean_p.startswith("+1236"):
        return "Canada"
    if clean_p.startswith("714") or clean_p.startswith("+1"):
        return "United States"
    if clean_p.startswith("+91") or (clean_p.isdigit() and len(clean_p) == 10 and clean_p[0] in ["8", "9"]):
        return "India"

    return default


class Command(BaseCommand):
    help = "Import distinct vendor users from DB Final mithun.xlsx (tab 'Confirmed - 221')"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="DB Final mithun.xlsx",
            help="Path to the Excel file",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default="Confirmed - 221",
            help="Name of the worksheet tab to process",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Inspect and simulate creation without saving to database",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        sheet_name = options["sheet"]
        dry_run = options["dry_run"]

        if not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(self.style.NOTICE(f"Loading workbook '{file_path}', tab '{sheet_name}'..."))
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        if sheet_name not in wb.sheetnames:
            self.stderr.write(self.style.ERROR(f"Sheet '{sheet_name}' not found. Available sheets: {wb.sheetnames}"))
            return

        sheet = wb[sheet_name]
        row_iter = sheet.iter_rows(values_only=True)
        first_row = next(row_iter, None)
        if not first_row:
            self.stderr.write(self.style.ERROR("Sheet is empty."))
            return

        headers = [str(c).strip() if c is not None else "" for c in first_row[:32]]
        self.stdout.write(f"Found {len(headers)} header columns.")

        try:
            idx_comp = headers.index("Company")
            idx_person = headers.index("Contact Person")
            idx_phone = headers.index("Contact No")
            idx_email = headers.index("Email")
            idx_cat = headers.index("Category")
        except ValueError as e:
            self.stderr.write(self.style.ERROR(f"Missing required header column: {e}"))
            return

        contacts_map = {}
        empty_streak = 0
        for r_idx, row in enumerate(row_iter, start=2):
            if not row or not any(row):
                empty_streak += 1
                if empty_streak >= 10:
                    break
                continue
            empty_streak = 0
            email_val = str(row[idx_email]).strip().lower() if row[idx_email] is not None else ""
            if not email_val:
                continue

            comp_val = str(row[idx_comp]).strip() if row[idx_comp] is not None else ""
            person_val = str(row[idx_person]).strip() if row[idx_person] is not None else ""
            phone_val = str(row[idx_phone]).strip() if row[idx_phone] is not None else ""
            cat_val = str(row[idx_cat]).strip() if row[idx_cat] is not None else ""

            if email_val not in contacts_map:
                contacts_map[email_val] = {
                    "company": comp_val,
                    "person": person_val,
                    "phone": phone_val,
                    "email": email_val,
                    "categories": set(),
                    "product_count": 0,
                }

            if cat_val:
                contacts_map[email_val]["categories"].add(cat_val)
            contacts_map[email_val]["product_count"] += 1

            # Backfill any richer contact data from subsequent rows if initial was blank
            if comp_val and not contacts_map[email_val]["company"]:
                contacts_map[email_val]["company"] = comp_val
            if person_val and not contacts_map[email_val]["person"]:
                contacts_map[email_val]["person"] = person_val
            if phone_val and not contacts_map[email_val]["phone"]:
                contacts_map[email_val]["phone"] = phone_val

        self.stdout.write(self.style.NOTICE(f"Identified {len(contacts_map)} unique vendor contacts in sheet."))

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for email, data in contacts_map.items():
            company = data["company"]
            person = data["person"]
            phone = data["phone"]
            categories = sorted(list(data["categories"]))
            product_count = data["product_count"]

            country = detect_country(phone, email, company)
            is_company = bool(company and company.lower() not in ["nil", "none", "n/a", ""])
            account_entity_type = "COMPANY" if is_company else "INDIVIDUAL"
            clean_company_name = company if is_company else ""

            # Check if vendor already exists by email
            existing_vendor = VendorDetails.objects.filter(email__iexact=email).first()
            if not existing_vendor and phone:
                existing_vendor = VendorDetails.objects.filter(mobile_number__iexact=phone).first()

            if existing_vendor:
                # Update any missing details on existing vendor
                modified = False
                if not existing_vendor.full_name and person:
                    existing_vendor.full_name = person
                    modified = True
                if not existing_vendor.company_name and clean_company_name:
                    existing_vendor.company_name = clean_company_name
                    modified = True
                if not existing_vendor.mobile_number and phone:
                    existing_vendor.mobile_number = phone
                    modified = True
                if categories:
                    cur_cats = existing_vendor.category_interested_list
                    merged_cats = sorted(list(set(cur_cats + categories)))
                    if merged_cats != cur_cats:
                        existing_vendor.category_interested = merged_cats
                        modified = True

                if modified and not dry_run:
                    existing_vendor.save()
                    updated_count += 1
                    self.stdout.write(f"Updated existing vendor: {existing_vendor.username} ({email})")
                else:
                    skipped_count += 1
                    self.stdout.write(f"Already exists: {existing_vendor.username} ({email}) - skipped.")
                continue

            # Generate unique, descriptive username
            email_user = email.split("@")[0].lower()
            email_domain = email.split("@")[1].split(".")[0].lower() if "@" in email else ""
            
            generic_prefixes = {"info", "sales", "contact", "retail", "support", "admin", "mail", "office", "marketing"}
            if email_user in generic_prefixes:
                if clean_company_name:
                    comp_slug = re.sub(r"[^a-zA-Z0-9_]", "_", clean_company_name.lower())[:15].strip("_")
                    base_uname = f"{comp_slug}_{email_user}"
                elif email_domain:
                    base_uname = f"{email_domain}_{email_user}"
                else:
                    base_uname = email_user
            else:
                base_uname = email_user

            base_uname = re.sub(r"[^a-zA-Z0-9_]", "_", base_uname).strip("_") or "vendor"
            uname = base_uname
            suffix = 1
            while VendorDetails.objects.filter(username__iexact=uname).exists():
                uname = f"{base_uname}_{suffix}"
                suffix += 1

            if dry_run:
                self.stdout.write(
                    f"[DRY-RUN] Would create: username='{uname}', name='{person}', email='{email}', "
                    f"phone='{phone}', company='{clean_company_name}', country='{country}', entity='{account_entity_type}'"
                )
                created_count += 1
                continue

            # Create VendorDetails user
            new_vendor = VendorDetails.objects.create(
                username=uname,
                full_name=person,
                email=email,
                mobile_number=phone,
                country=country,
                account_entity_type=account_entity_type,
                company_name=clean_company_name,
                business_location=country,
                business_type=categories[0] if categories else "",
                category_interested=categories,
                user_type="SELLER",
                pass_word=VendorDetails.hash_password("Surplus@2026"),
                status=True,
            )
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created [{new_vendor.vendor_id}]: {new_vendor.username} | {new_vendor.full_name} | {new_vendor.email} | {new_vendor.company_name} ({country})"
                )
            )

        mode_str = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode_str}Complete! Created: {created_count}, Updated: {updated_count}, Skipped: {skipped_count}."
            )
        )
