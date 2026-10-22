import os
import urllib.parse
from django.conf import settings
from django.core.files.storage import default_storage


def resolve_media_url(img_val):
    """
    Given an image value (URL, storage path, dict, etc.), return a valid, freshly signed URL.
    Safely resolves:
    - Cloudflare R2 / AWS S3 presigned URLs with expired or temporary tokens (?X-Amz-Algorithm=...).
    - Relative paths (e.g. 'lots/images/xyz.png' or '/media/lots/images/xyz.png').
    - Standard third-party image URLs.
    - Prevents double URL-encoding (%20 -> %2520) for filenames with spaces.
    """
    if not img_val:
        return ""
    if isinstance(img_val, dict):
        img_val = img_val.get("url") or img_val.get("src") or img_val.get("image") or img_val.get("file_url") or ""
    
    s = str(img_val).strip()
    if not s:
        return ""

    # Always unquote clean path first to avoid double-encoding (%20 -> %2520)
    clean_path_raw = s.split("?")[0]
    clean_path = urllib.parse.unquote(urllib.parse.unquote(clean_path_raw))
    filename = clean_path.replace("\\", "/").split("/")[-1]

    is_s3_presigned = any(k in s for k in ("X-Amz-Algorithm", "X-Amz-Credential", "r2.cloudflarestorage.com", "amazonaws.com"))
    if (s.startswith("http://") or s.startswith("https://") or s.startswith("//")) and not is_s3_presigned:
        return s

    rel_key = None
    for marker in ("/media/", "/app-staging-media/media/", "/app-staging-media/"):
        if marker in clean_path:
            rel_key = clean_path.split(marker, 1)[-1].lstrip("/")
            break

    if not rel_key:
        for prefix in ("lots/images/", "lots/documents/", "enquiries/lots/", "products/"):
            if prefix in clean_path:
                rel_key = prefix + clean_path.split(prefix, 1)[-1]
                break

    if not rel_key:
        if not s.startswith("http://") and not s.startswith("https://") and not s.startswith("//"):
            rel = clean_path.lstrip("/")
            if rel.startswith("media/"):
                rel = rel[6:]
            rel_key = rel
        else:
            rel_key = f"lots/images/{filename}" if filename else None

    if rel_key:
        try:
            return default_storage.url(rel_key)
        except Exception:
            pass

    if filename:
        for cand in (f"lots/images/{filename}", f"enquiries/lots/{filename}", f"products/{filename}", filename):
            try:
                if default_storage.exists(cand):
                    return default_storage.url(cand)
            except Exception:
                pass

    fallback_rel = rel_key or filename or ""
    from django.utils.encoding import filepath_to_uri
    return f"{settings.MEDIA_URL}{filepath_to_uri(fallback_rel.lstrip('/'))}"

