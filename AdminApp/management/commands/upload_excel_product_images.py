import os
import sys
import re
import urllib.parse
from django.core.management.base import BaseCommand
from django.core.files import File
from django.db.models.signals import post_save
import openpyxl

from AdminApp.models import Product, ProductImage, VendorDetails

# Fix Windows console charmap encoding issues for international product names
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class Command(BaseCommand):
    help = "Check product_images directory and upload/attach image files for products matching image names from Excel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="DB Final mithun.xlsx",
            help="Path to the Excel file (default: DB Final mithun.xlsx)",
        )
        parser.add_argument(
            "--sheet",
            type=str,
            default="Confirmed - 221",
            help="Name of worksheet tab to process (default: Confirmed - 221)",
        )
        parser.add_argument(
            "--all-sheets",
            action="store_true",
            help="Process all sheets in the Excel file",
        )
        parser.add_argument(
            "--all-db",
            action="store_true",
            help="Update all existing ProductImage records in database whose image field is empty",
        )
        parser.add_argument(
            "--images-dir",
            type=str,
            default="product_images",
            help="Directory containing the product images (default: product_images)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the upload without making changes to the database or files",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limit number of rows/products to process",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        sheet_name = options["sheet"]
        all_sheets = options["all_sheets"]
        all_db = options["all_db"]
        images_dir = options["images_dir"]
        dry_run = options["dry_run"]
        limit = options["limit"]

        # 1. Index local image directory
        self.stdout.write(self.style.NOTICE(f"Indexing local images directory '{images_dir}'..."))
        if not os.path.exists(images_dir):
            self.stderr.write(self.style.ERROR(f"Directory not found: '{images_dir}'"))
            return

        exact_map = {}
        lower_map = {}
        for fname in os.listdir(images_dir):
            full_p = os.path.join(images_dir, fname)
            if os.path.isfile(full_p):
                exact_map[fname] = full_p
                lower_map[fname.lower()] = full_p

        self.stdout.write(self.style.SUCCESS(f"Indexed {len(exact_map)} images from '{images_dir}'."))

        # Secondary search directories
        secondary_dirs = [
            "media/product_images",
            "media/email_enq_images",
            "media/uploaded_images",
            "d:/CORALBEES/surplusmui/surplusmui/media/product_images",
            "d:/CORALBEES/surplusmui/surplusmui/media/email_enq_images",
            "d:/CORALBEES/surplusmui/surplusmui/media/uploaded_images",
        ]

        def resolve_image_file(raw_url):
            if not raw_url:
                return None, None
            decoded = urllib.parse.unquote(str(raw_url).strip())
            fname = os.path.basename(decoded)
            if not fname:
                return None, None

            # 1. Direct check in images_dir
            if fname in exact_map:
                return exact_map[fname], fname
            if fname.lower() in lower_map:
                return lower_map[fname.lower()], fname

            # 2. Check if direct path under project root exists
            direct_cand = decoded.lstrip("/")
            if os.path.exists(direct_cand) and os.path.isfile(direct_cand):
                return direct_cand, fname

            # 3. Check secondary directories
            for sdir in secondary_dirs:
                if os.path.exists(sdir) and os.path.isdir(sdir):
                    cand = os.path.join(sdir, fname)
                    if os.path.exists(cand) and os.path.isfile(cand):
                        return cand, fname
                    cand_lower = os.path.join(sdir, fname.lower())
                    if os.path.exists(cand_lower) and os.path.isfile(cand_lower):
                        return cand_lower, fname

            return None, fname

        # Disconnect signals to prevent slow external API/Typesense timeouts during bulk upload
        from AdminApp.signals import product_post_save_sync, product_image_post_save_sync
        import AdminApp.semantic_search as sem_search

        orig_sync_emb = getattr(sem_search, "sync_product_embedding", None)
        sem_search.sync_product_embedding = lambda *a, **kw: (None, False)
        post_save.disconnect(product_post_save_sync, sender=Product)
        post_save.disconnect(product_image_post_save_sync, sender=ProductImage)

        try:
            if all_db:
                self.stdout.write(self.style.NOTICE("Running update for all existing ProductImage records in database..."))
                self._update_all_db(resolve_image_file, dry_run, limit)
            else:
                if not os.path.exists(file_path):
                    self.stderr.write(self.style.ERROR(f"Excel file not found: '{file_path}'"))
                    return
                self._process_excel(file_path, sheet_name, all_sheets, resolve_image_file, dry_run, limit)
        finally:
            if orig_sync_emb:
                sem_search.sync_product_embedding = orig_sync_emb
            post_save.connect(product_post_save_sync, sender=Product)
            post_save.connect(product_image_post_save_sync, sender=ProductImage)

    def _process_excel(self, file_path, sheet_name, all_sheets, resolve_image_file, dry_run, limit):
        # Pre-cache all products and their existing images in memory (1 single DB query)
        self.stdout.write(self.style.NOTICE("Caching existing products and images from database in memory..."))
        all_prods = list(Product.objects.all().prefetch_related("images").select_related("vendor"))
        self.stdout.write(f"Cached {len(all_prods)} products from database.")

        prods_by_pid = {}
        prods_by_vendor_name = {}
        prods_by_name_model = {}
        prods_by_name = {}

        for p in all_prods:
            if p.product_id:
                prods_by_pid[p.product_id.strip()] = p
            v_email = p.vendor.email.lower().strip() if p.vendor and p.vendor.email else ""
            p_name = p.product_name.lower().strip()
            p_model = p.model_no.lower().strip() if p.model_no else ""
            if v_email:
                prods_by_vendor_name[(v_email, p_name)] = p
            if p_model:
                prods_by_name_model[(p_name, p_model)] = p
            prods_by_name[p_name] = p

        self.stdout.write(self.style.NOTICE(f"Loading '{file_path}'..."))
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheets_to_process = wb.sheetnames if all_sheets else [sheet_name]

        total_uploaded = 0
        total_already_set = 0
        total_missing = 0
        total_prods_matched = 0

        for sname in sheets_to_process:
            if sname not in wb.sheetnames:
                self.stderr.write(self.style.WARNING(f"Sheet '{sname}' not found, skipping."))
                continue

            self.stdout.write(self.style.NOTICE(f"\nProcessing sheet '{sname}'..."))
            sheet = wb[sname]
            row_iter = sheet.iter_rows(values_only=True)
            first_row = next(row_iter, None)
            if not first_row:
                continue

            headers = [str(c).strip() if c is not None else "" for c in first_row]
            col_idx = {h: i for i, h in enumerate(headers) if h}

            pname_col = col_idx.get("Product Name")
            model_col = col_idx.get("Model / Part No")
            pid_col = col_idx.get("Product ID")
            email_col = col_idx.get("Email")
            feat_col = col_idx.get("Featured Image URL")
            all_col = col_idx.get("All Image URLs")

            if feat_col is None and all_col is None:
                self.stderr.write(self.style.WARNING(f"Sheet '{sname}' has no image URL columns. Skipping."))
                continue

            sheet_rows = 0
            for r_vals in row_iter:
                if not r_vals or not any(x is not None and str(x).strip() != "" for x in r_vals):
                    continue

                if limit and sheet_rows >= limit:
                    break
                sheet_rows += 1

                pname = str(r_vals[pname_col]).strip() if pname_col is not None and pname_col < len(r_vals) and r_vals[pname_col] else ""
                model = str(r_vals[model_col]).strip() if model_col is not None and model_col < len(r_vals) and r_vals[model_col] else ""
                pid = str(r_vals[pid_col]).strip() if pid_col is not None and pid_col < len(r_vals) and r_vals[pid_col] else ""
                email = str(r_vals[email_col]).strip().lower() if email_col is not None and email_col < len(r_vals) and r_vals[email_col] else ""

                if not pname:
                    continue

                # Fast O(1) in-memory lookup
                product = None
                if pid and pid in prods_by_pid:
                    product = prods_by_pid[pid]
                if not product and email and (email, pname.lower()) in prods_by_vendor_name:
                    product = prods_by_vendor_name[(email, pname.lower())]
                if not product and model and (pname.lower(), model.lower()) in prods_by_name_model:
                    product = prods_by_name_model[(pname.lower(), model.lower())]
                if not product and pname.lower() in prods_by_name:
                    product = prods_by_name[pname.lower()]

                if not product:
                    continue

                total_prods_matched += 1

                # Collect all image URLs from this row
                row_urls = []
                if feat_col is not None and feat_col < len(r_vals) and r_vals[feat_col]:
                    val = str(r_vals[feat_col]).strip()
                    if val.lower() not in ["none", "nil", "n/a", ""]:
                        row_urls.append(val)

                if all_col is not None and all_col < len(r_vals) and r_vals[all_col]:
                    val = str(r_vals[all_col]).strip()
                    if val.lower() not in ["none", "nil", "n/a", ""]:
                        for u in val.split(","):
                            u_str = u.strip()
                            if u_str and u_str not in row_urls and u_str.lower() not in ["none", "nil", "n/a"]:
                                row_urls.append(u_str)

                # Pre-fetch existing images of this product
                existing_imgs = list(product.images.all())

                for u in row_urls:
                    local_path, fname = resolve_image_file(u)
                    if not local_path:
                        total_missing += 1
                        continue

                    # Check if ProductImage already exists for this product
                    existing_pi = None
                    fname_lower = fname.lower()
                    for pi_item in existing_imgs:
                        pi_img_name = (pi_item.image.name or "").lower() if pi_item.image else ""
                        pi_url = (pi_item.image_url or "").lower()
                        if fname_lower in pi_img_name or fname_lower in pi_url:
                            existing_pi = pi_item
                            break

                    if existing_pi and existing_pi.image and existing_pi.image.name:
                        total_already_set += 1
                        continue

                    if dry_run:
                        self.stdout.write(f"[DRY-RUN] Would attach '{local_path}' to {product.product_id} ('{pname}')")
                        total_uploaded += 1
                        continue

                    # Attach and upload image to product
                    try:
                        with open(local_path, "rb") as f_obj:
                            django_file = File(f_obj, name=fname)
                            if existing_pi:
                                existing_pi.image.save(fname, django_file, save=False)
                                existing_pi.image_url = existing_pi.image.url
                                existing_pi.is_real_photo = True
                                existing_pi.save(update_fields=["image", "image_url", "is_real_photo"])
                            else:
                                new_pi = ProductImage(product=product, is_real_photo=True)
                                new_pi.image.save(fname, django_file, save=False)
                                new_pi.image_url = new_pi.image.url
                                new_pi.save()
                                existing_imgs.append(new_pi)
                        total_uploaded += 1
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error saving image '{fname}' for {product.product_id}: {e}"))

            self.stdout.write(
                self.style.SUCCESS(
                    f"Sheet '{sname}' complete. Rows processed: {sheet_rows}. "
                    f"Uploaded/Attached: {total_uploaded}, Already set: {total_already_set}, Missing: {total_missing}."
                )
            )

        wb.close()
        mode_str = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode_str}Finished Excel image upload! "
                f"Products matched: {total_prods_matched}, "
                f"Images uploaded/attached: {total_uploaded}, "
                f"Already had image: {total_already_set}, "
                f"Missing in product_images: {total_missing}."
            )
        )

    def _update_all_db(self, resolve_image_file, dry_run, limit):
        qs = ProductImage.objects.all().select_related("product")
        total = qs.count()
        self.stdout.write(f"Total ProductImage records in database: {total}")

        uploaded = 0
        already_has_image = 0
        missing = 0
        count = 0

        for pi in qs:
            count += 1
            if limit and count > limit:
                break

            if pi.image and pi.image.name:
                already_has_image += 1
                continue

            local_path, fname = resolve_image_file(pi.image_url)
            if not local_path:
                missing += 1
                continue

            if dry_run:
                self.stdout.write(f"[DRY-RUN] Would attach '{local_path}' to PI #{pi.id} (Product: {pi.product.product_name})")
                uploaded += 1
                continue

            try:
                with open(local_path, "rb") as f_obj:
                    django_file = File(f_obj, name=fname)
                    pi.image.save(fname, django_file, save=False)
                    pi.image_url = pi.image.url
                    pi.is_real_photo = True
                    pi.save(update_fields=["image", "image_url", "is_real_photo"])
                uploaded += 1
                if uploaded % 25 == 0:
                    self.stdout.write(f"  Attached {uploaded} images...")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error saving image '{fname}' for PI #{pi.id}: {e}"))

        mode_str = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode_str}Database update complete! "
                f"Uploaded/Attached: {uploaded}, "
                f"Already had image: {already_has_image}, "
                f"Missing on disk: {missing}."
            )
        )
