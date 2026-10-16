"""
Management command to process the transactional outbox queue for Typesense synchronization.
Usage:
  python manage.py sync_typesense_outbox [--max-retries=5] [--limit=50]
"""

import logging
from django.core.management.base import BaseCommand
from AdminApp.models import TypesenseSyncQueue, Product, Lot
from AdminApp.typesense_service import (
    is_typesense_available,
    index_product,
    delete_product,
    index_lot,
    delete_lot,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Processes pending sync items from the TypesenseSyncQueue outbox."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-retries",
            type=int,
            default=5,
            help="Maximum retry attempts before skipping an item (default: 5).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Maximum items to process in this run (default: 100).",
        )

    def handle(self, *args, **options):
        max_retries = options["max_retries"]
        limit = options["limit"]

        is_healthy, msg = is_typesense_available()
        if not is_healthy:
            self.stdout.write(
                self.style.WARNING(f"[WARN] Typesense is unreachable ({msg}). Skipping outbox sync run.")
            )
            return

        pending_items = (
            TypesenseSyncQueue.objects.filter(processed=False, attempts__lt=max_retries)
            .order_by("created_at")[:limit]
        )
        count = pending_items.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("[OK] No pending items in Typesense outbox queue."))
            return

        self.stdout.write(self.style.NOTICE(f"[INFO] Processing {count} pending Typesense outbox items..."))

        success_count = 0
        error_count = 0

        for item in pending_items:
            success = False
            error_message = ""
            try:
                if item.entity_type == "product":
                    if item.action == "delete":
                        success = delete_product(item.entity_id)
                    else:
                        try:
                            prod = Product.objects.get(id=item.entity_id)
                            success = index_product(prod)
                        except Product.DoesNotExist:
                            # Product was deleted from DB, delete from Typesense
                            success = delete_product(item.entity_id)

                elif item.entity_type == "lot":
                    if item.action == "delete":
                        success = delete_lot(item.entity_id)
                    else:
                        try:
                            lot = Lot.objects.get(id=item.entity_id)
                            success = index_lot(lot)
                        except Lot.DoesNotExist:
                            # Lot was deleted from DB, delete from Typesense
                            success = delete_lot(item.entity_id)

            except Exception as e:
                error_message = str(e)
                success = False

            if success:
                item.processed = True
                item.last_error = ""
                item.save(update_fields=["processed", "last_error", "updated_at"])
                success_count += 1
            else:
                item.attempts += 1
                if error_message:
                    item.last_error = error_message[:1000]
                item.save(update_fields=["attempts", "last_error", "updated_at"])
                error_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"[OK] Outbox sync complete: {success_count} processed successfully, {error_count} failed/retried."
            )
        )
