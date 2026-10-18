from django.core.management.base import BaseCommand
from AdminApp.models import Product
from AdminApp.semantic_search import sync_product_embedding


class Command(BaseCommand):
    help = "Generates or updates 768-dimensional pgvector semantic embeddings for all products in Neon DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-generation of embeddings even if content hash is unchanged",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        products = Product.objects.all().order_by("id")
        total = products.count()

        self.stdout.write(self.style.NOTICE(f"Generating pgvector embeddings for {total} products (force={force})..."))

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for p in products:
            try:
                rec, was_updated = sync_product_embedding(p, force=force)
                if was_updated:
                    updated_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to embed Product #{p.id} ({p.product_name}): {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"Embeddings sync completed! Updated/Embedded: {updated_count}, Skipped (unchanged): {skipped_count}, Total: {total}"
        ))
