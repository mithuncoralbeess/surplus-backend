"""
Django signals for real-time Typesense synchronization.
Uses transaction.on_commit to ensure database operations succeed before syncing.
Safe on network error: catches exceptions and delegates to TypesenseSyncQueue outbox.
"""

import logging
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Product, Lot, ProductImage, VendorDetails
from .typesense_service import index_product, delete_product, index_lot, delete_lot

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
def product_post_save_sync(sender, instance, **kwargs):
    """
    On product save/update, synchronize document with Typesense after DB transaction commits.
    """
    def _sync():
        try:
            index_product(instance)
        except Exception as e:
            logger.error(f"Error in product post_save Typesense sync (#{instance.id}): {e}")

    transaction.on_commit(_sync)


@receiver(post_delete, sender=Product)
def product_post_delete_sync(sender, instance, **kwargs):
    """
    On product deletion, purge document from Typesense after DB transaction commits.
    """
    prod_id = instance.id

    def _sync():
        try:
            delete_product(prod_id)
        except Exception as e:
            logger.error(f"Error in product post_delete Typesense sync (#{prod_id}): {e}")

    transaction.on_commit(_sync)


@receiver(post_save, sender=Lot)
def lot_post_save_sync(sender, instance, **kwargs):
    """
    On lot save/update, synchronize document with Typesense after DB transaction commits.
    """
    def _sync():
        try:
            index_lot(instance)
        except Exception as e:
            logger.error(f"Error in lot post_save Typesense sync (#{instance.id}): {e}")

    transaction.on_commit(_sync)


@receiver(post_delete, sender=Lot)
def lot_post_delete_sync(sender, instance, **kwargs):
    """
    On lot deletion, purge document from Typesense after DB transaction commits.
    """
    lot_id = instance.id

    def _sync():
        try:
            delete_lot(lot_id)
        except Exception as e:
            logger.error(f"Error in lot post_delete Typesense sync (#{lot_id}): {e}")

    transaction.on_commit(_sync)


@receiver(post_save, sender=ProductImage)
def product_image_post_save_sync(sender, instance, **kwargs):
    """
    When product images are added or modified, re-index parent product.
    """
    if instance.product:
        def _sync():
            try:
                index_product(instance.product)
            except Exception as e:
                logger.error(f"Error re-indexing product after image update (#{instance.product_id}): {e}")

        transaction.on_commit(_sync)


@receiver(post_delete, sender=ProductImage)
def product_image_post_delete_sync(sender, instance, **kwargs):
    """
    When product images are deleted, re-index parent product.
    """
    if instance.product:
        def _sync():
            try:
                index_product(instance.product)
            except Exception as e:
                logger.error(f"Error re-indexing product after image removal (#{instance.product_id}): {e}")

        transaction.on_commit(_sync)


@receiver(post_delete, sender=VendorDetails)
def vendor_post_delete_handler(sender, instance, **kwargs):
    """
    When vendors are deleted:
    - If no vendors remain in DB, reset sequence to 1 (is_called=False), so next vendor gets USR-0001.
    - If vendors remain, ensure sequence is aligned with the max ID so no gaps or duplicates occur.
    """
    def _align_seq():
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                max_id = VendorDetails.objects.order_by("-id").values_list("id", flat=True).first()
                if not max_id:
                    cursor.execute("SELECT setval('vendor_details_id_seq', 1, false);")
                    logger.info("[Sequence] vendor_details_id_seq reset to 1 (no vendors remaining).")
                else:
                    cursor.execute("SELECT setval('vendor_details_id_seq', %s, true);", [max_id])
                    logger.info(f"[Sequence] vendor_details_id_seq aligned to max ID {max_id}.")
        except Exception as e:
            logger.error(f"Error aligning vendor_details_id_seq on post_delete: {e}")

    transaction.on_commit(_align_seq)

