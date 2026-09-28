import sass
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Compiles SCSS files in templates/static/scss to CSS in templates/static/css"

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        scss_dir = base_dir / "AdminApp" / "templates" / "static" / "scss"
        css_dir = base_dir / "AdminApp" / "templates" / "static" / "css"

        css_dir.mkdir(parents=True, exist_ok=True)

        for scss_file in scss_dir.glob("*.scss"):
            if scss_file.name.startswith("_"):
                continue  # Skip partials

            css_filename = scss_file.stem + ".css"
            css_file = css_dir / css_filename

            compiled_css = sass.compile(
                filename=str(scss_file),
                output_style="expanded",
            )
            css_file.write_text(compiled_css, encoding="utf-8")
            self.stdout.write(
                self.style.SUCCESS(f"Compiled {scss_file.name} -> {css_filename}")
            )
