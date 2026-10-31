import os, sys, django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
cursor = connection.cursor()

cursor.execute("SELECT max(id) FROM lot_products")
print("Max id:", cursor.fetchone())

cursor.execute("SELECT max(CAST(SUBSTRING(product_id FROM 5) AS INTEGER)) FROM lot_products WHERE product_id LIKE 'BLK-%'")
print("Max BLK number:", cursor.fetchone())

cursor.execute("SELECT last_value FROM lot_products_id_seq")
print("Sequence last_value:", cursor.fetchone())

