import re
from django.db import migrations


SUFFIX_RE = re.compile(r"\s*\|\s*Surplus Market\s*$", re.IGNORECASE)


def strip_surplus_market_suffix(apps, schema_editor):
    """Remove trailing '| Surplus Market' suffix from existing ContentPage and BlogPost meta_title values."""
    ContentPage = apps.get_model("AdminApp", "ContentPage")
    BlogPost = apps.get_model("AdminApp", "BlogPost")

    for model_cls in (ContentPage, BlogPost):
        for obj in model_cls.objects.exclude(meta_title="").only("id", "meta_title"):
            current = obj.meta_title or ""
            cleaned = SUFFIX_RE.sub("", current).strip()
            if cleaned != current:
                model_cls.objects.filter(pk=obj.pk).update(meta_title=cleaned)


class Migration(migrations.Migration):

    dependencies = [
        ("AdminApp", "0078_regenerate_product_codes"),
    ]

    operations = [
        migrations.RunPython(strip_surplus_market_suffix, migrations.RunPython.noop),
    ]

