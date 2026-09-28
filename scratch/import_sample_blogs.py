import os
import sys
import json
import django

# Setup Django environment
sys.path.append("d:/CORALBEES/surplus-backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from AdminApp.models import BlogPost

def import_blogs():
    from pathlib import Path
    from django.conf import settings

    sample_dir = settings.BASE_DIR / "sample-blog"
    json_file = sample_dir / "all_blogs.json"
    if not json_file.exists():
        json_file = sample_dir / "blogs.json"

    blogs_data = []

    if json_file.exists():
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                blogs_data = json.load(f)
                print(f"Loaded {len(blogs_data)} blogs from {json_file.name}")
        except Exception as e:
            print(f"Error reading {json_file}: {e}")

    # Fallback to individual blog_*.json files if main file empty
    if not blogs_data:
        for p in sample_dir.glob("blog_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    item = json.load(f)
                    if isinstance(item, dict):
                        blogs_data.append(item)
            except Exception as e:
                print(f"Error reading {p.name}: {e}")
        print(f"Loaded {len(blogs_data)} individual blog JSON files")

    imported_count = 0
    updated_count = 0

    for item in blogs_data:
        title = item.get("title", "").strip()
        if not title:
            continue
        slug = item.get("slug") or title.lower().replace(" ", "-")
        blog_code = item.get("blog_code") or f"BLOG-{item.get('id', 1):03d}"
        content = item.get("content") or ""
        excerpt = item.get("excerpt") or ""
        author = item.get("author") or "Admin"
        category_name = item.get("category_name") or item.get("category") or "General"
        
        img_raw = item.get("image") or item.get("featured_image_url") or ""
        if img_raw:
            if img_raw.startswith("http://") or img_raw.startswith("https://") or img_raw.startswith("/"):
                img = img_raw
            else:
                img = f"/media/{img_raw}"
        else:
            img = ""

        meta_t = item.get("meta_tags") or item.get("meta_title") or title
        meta_d = item.get("meta_description") or ""
        read_t = int(item.get("read_time") or 3)
        total_r = int(item.get("total_reads") or 0)
        is_pub = item.get("is_published", True)

        blog, created = BlogPost.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "blog_code": blog_code,
                "author": author,
                "category_name": category_name,
                "excerpt": excerpt,
                "content": content,
                "featured_image_url": img,
                "meta_title": meta_t,
                "meta_description": meta_d,
                "read_time": read_t,
                "total_reads": total_r,
                "status": "published" if is_pub else "draft"
            }
        )
        if created:
            imported_count += 1
        else:
            updated_count += 1

    print(f"Import complete! Created: {imported_count}, Updated: {updated_count}, Total in DB: {BlogPost.objects.count()}")

if __name__ == "__main__":
    import_blogs()
