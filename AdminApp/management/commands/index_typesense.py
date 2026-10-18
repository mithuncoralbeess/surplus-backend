"""
Management command to initialize and index Surplus Market products and lots into Typesense.
Usage:
  python manage.py index_typesense [--recreate] [--batch-size=100] [--type=all|product|lot]
"""

import time
from django.core.management.base import BaseCommand
from AdminApp.models import Product, Lot
from AdminApp.typesense_service import (
    is_typesense_available,
    init_collection,
    product_to_document,
    lot_to_document,
    bulk_index_documents,
    get_collection_name,
)


class Command(BaseCommand):
    help = "Initializes Typesense collection and indexes all approved active products and wholesale lots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recreate",
            action="store_true",
            help="Drop and recreate the Typesense collection schema before indexing.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of documents to import per bulk batch (default: 100).",
        )
        parser.add_argument(
            "--type",
            type=str,
            default="all",
            choices=["all", "product", "lot"],
            help="Entity type to index: 'all', 'product', or 'lot'.",
        )

    def handle(self, *args, **options):
        start_time = time.time()
        recreate = options["recreate"]
        batch_size = options["batch_size"]
        entity_type = options["type"]

        self.stdout.write(self.style.NOTICE("[INFO] Checking Typesense cluster status..."))
        is_healthy, status_msg = is_typesense_available()
        if not is_healthy:
            self.stdout.write(
                self.style.ERROR(
                    f"[ERROR] Cannot connect to Typesense: {status_msg}\n"
                    f"Please ensure Typesense is running (e.g. via 'docker compose -f docker-compose.typesense.yml up -d')."
                )
            )
            return

        self.stdout.write(self.style.SUCCESS(f"[OK] Typesense is healthy ({status_msg})."))
        coll_name = get_collection_name()

        self.stdout.write(self.style.NOTICE(f"[INFO] Initializing collection '{coll_name}' (recreate={recreate})..."))
        if not init_collection(recreate=recreate):
            self.stdout.write(self.style.ERROR(f"[ERROR] Failed to initialize collection '{coll_name}'."))
            return

        total_products_indexed = 0
        total_lots_indexed = 0

        # 1. Index Products
        if entity_type in ("all", "product"):
            self.stdout.write(self.style.NOTICE("[INFO] Fetching approved active products from PostgreSQL..."))
            products_qs = (
                Product.objects.filter(is_active=True, enquiry_status__iexact="APPROVED")
                .select_related("category", "subcategory")
                .prefetch_related("images")
                .order_by("id")
            )
            total_prods = products_qs.count()
            self.stdout.write(f"Found {total_prods} approved active product(s).")

            docs = []
            for p in products_qs.iterator(chunk_size=batch_size):
                doc = product_to_document(p)
                if doc:
                    docs.append(doc)

                if len(docs) >= batch_size:
                    s_count, err_count = bulk_index_documents(docs, batch_size=batch_size)
                    total_products_indexed += s_count
                    self.stdout.write(f"  Indexed {total_products_indexed}/{total_prods} products...")
                    docs = []

            if docs:
                s_count, _ = bulk_index_documents(docs, batch_size=batch_size)
                total_products_indexed += s_count

            self.stdout.write(self.style.SUCCESS(f"[OK] Successfully indexed {total_products_indexed} product(s)."))

        # 2. Index Lots
        if entity_type in ("all", "lot"):
            self.stdout.write(self.style.NOTICE("[INFO] Fetching approved active wholesale lots from PostgreSQL..."))
            lots_qs = (
                Lot.objects.filter(is_active=True, enquiry_status__iexact="approved")
                .order_by("id")
            )
            total_lots = lots_qs.count()
            self.stdout.write(f"Found {total_lots} approved active lot(s).")

            lot_docs = []
            for lot in lots_qs.iterator(chunk_size=batch_size):
                doc = lot_to_document(lot)
                if doc:
                    lot_docs.append(doc)

                if len(lot_docs) >= batch_size:
                    s_count, err_count = bulk_index_documents(lot_docs, batch_size=batch_size)
                    total_lots_indexed += s_count
                    self.stdout.write(f"  Indexed {total_lots_indexed}/{total_lots} lots...")
                    lot_docs = []

            if lot_docs:
                s_count, _ = bulk_index_documents(lot_docs, batch_size=batch_size)
                total_lots_indexed += s_count

            self.stdout.write(self.style.SUCCESS(f"[OK] Successfully indexed {total_lots_indexed} lot(s)."))

        elapsed = round(time.time() - start_time, 2)
        total_indexed = total_products_indexed + total_lots_indexed
        self.stdout.write(
            self.style.SUCCESS(
                f"\n[DONE] Typesense indexing finished in {elapsed}s!\n"
                f"       Total listings indexed: {total_indexed} ({total_products_indexed} products, {total_lots_indexed} lots)"
            )
        )
