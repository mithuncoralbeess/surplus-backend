import os
import sys
import django

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.apps import apps
from django.db import transaction

def clear_data():
    print("=== Starting Cleanup of Product, Lot, Enquiry, and Vendor User Data ===")
    
    # Models to explicitly preserve:
    PRESERVED_MODELS = {
        "AdminDetails",
        "AdminPasswordResetOTP",
        "ContentPage",
        "ContentBlog",
        "SystemSettings",
        "MaintenanceMode",
        "LogEntry",
        "Permission",
        "Group",
        "User",
        "ContentType",
        "Session",
        "Migration"
    }

    count_summary = {}

    with transaction.atomic():
        # Iterate over installed apps (specifically AdminApp and api)
        for app_label in ["AdminApp", "api"]:
            try:
                app_config = apps.get_app_config(app_label)
            except KeyError:
                continue
                
            for model in app_config.get_models():
                model_name = model.__name__
                table_name = model._meta.db_table
                
                if model_name in PRESERVED_MODELS:
                    print(f"[PRESERVED] Skipping {model_name} ({table_name})")
                    continue
                
                try:
                    deleted_count, _ = model.objects.all().delete()
                    count_summary[f"{app_label}.{model_name}"] = deleted_count
                    print(f"[CLEARED] Removed {deleted_count} records from {model_name}")
                except Exception as e:
                    print(f"[ERROR] Failed to clear {model_name}: {e}")

    print("\n=== Cleanup Summary ===")
    for model_path, count in count_summary.items():
        print(f" - {model_path}: {count} deleted")
    print("=== Complete ===")

if __name__ == "__main__":
    clear_data()
