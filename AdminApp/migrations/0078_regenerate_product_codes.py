import re
import secrets
import string
from django.db import migrations


def _random_code() -> str:
    digits = "".join(secrets.choice(string.digits) for _ in range(3))
    letters = "".join(secrets.choice(string.ascii_uppercase) for _ in range(3))
    return f"{digits}{letters}"


def regenerate_product_codes(apps, schema_editor):
    """
    Replace auto-copied product_id values in Product.product_code with unique
    '861YWZ'-format codes (3 digits + 3 uppercase letters). Leaves Product.product_id untouched.
    """
    Product = apps.get_model("AdminApp", "Product")
    rows = list(Product.objects.all().order_by("id").only("id", "product_id", "product_code"))

    seen_codes = set()
    to_regenerate = []

    for row in rows:
        pid = (row.product_id or "").strip()
        pcode = (row.product_code or "").strip()
        copied_from_id = bool(pcode) and pcode.upper() == pid.upper()
        legacy_pro = bool(re.match(r"^PRO-\d+$", pcode, re.IGNORECASE))

        if not pcode or copied_from_id or legacy_pro or pcode.upper() in seen_codes:
            to_regenerate.append(row)
        else:
            seen_codes.add(pcode.upper())

    for row in to_regenerate:
        candidate = _random_code()
        while candidate.upper() in seen_codes:
            candidate = _random_code()
        seen_codes.add(candidate.upper())
        Product.objects.filter(pk=row.pk).update(product_code=candidate)


class Migration(migrations.Migration):

    dependencies = [
        ("AdminApp", "0077_product_product_code_alter_product_enquiry_status_and_more"),
    ]

    operations = [
        migrations.RunPython(regenerate_product_codes, migrations.RunPython.noop),
    ]

