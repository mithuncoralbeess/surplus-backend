#!/usr/bin/env python3
"""
FTP Deployment Script for Surplus Backend.
Deploys project code to the specified FTP server, excluding system and cache files,
and triggers Passenger WSGI application restart.
"""

import os
import sys
import ftplib
import io
import time
import fnmatch

# Configuration from Environment Variables with sensible defaults
FTP_HOST = os.getenv("FTP_HOST", "69.48.190.126")
FTP_USER = os.getenv("FTP_USER", "mazin@dev.surplusmarket.com")
FTP_PASS = os.getenv("FTP_PASS", os.getenv("FTP_PASSWORD", "MithuFtp@123"))
FTP_BASE = os.getenv("FTP_BASE", "/public_html/surplusmui").rstrip("/")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Patterns and directories to exclude from upload
EXCLUDE_DIRS = {
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "scratch",
    "media",
    ".idea",
    ".vscode",
}

EXCLUDE_FILE_PATTERNS = [
    ".env",
    ".env.*",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.log",
    "*.xlsx",
    "*.sqlite3",
    ".DS_Store",
    "Thumbs.db",
]


def should_exclude_dir(dir_name: str) -> bool:
    return dir_name in EXCLUDE_DIRS or dir_name.startswith(".git")


def should_exclude_file(file_name: str) -> bool:
    for pattern in EXCLUDE_FILE_PATTERNS:
        if fnmatch.fnmatch(file_name, pattern):
            return True
    return False


def ensure_remote_dir(ftp: ftplib.FTP, remote_path: str):
    """
    Ensures that a remote directory exists by walking path components.
    """
    parts = [p for p in remote_path.replace("\\", "/").split("/") if p]
    current = ""
    for part in parts:
        current += "/" + part
        try:
            ftp.cwd(current)
        except ftplib.error_perm:
            try:
                ftp.mkd(current)
                print(f"[DIR CREATED] {current}")
            except Exception as e:
                # Directory might have been created concurrently or already exists
                pass


def upload_directory(ftp: ftplib.FTP, local_root: str, remote_root: str):
    """
    Recursively uploads files from local_root to remote_root.
    """
    total_uploaded = 0
    total_skipped = 0

    print(f"[*] Starting upload from: {local_root}")
    print(f"[*] Remote target directory: {remote_root}")

    ensure_remote_dir(ftp, remote_root)

    for root, dirs, files in os.walk(local_root):
        # Filter directories in-place so os.walk does not descend into excluded dirs
        dirs[:] = [d for d in dirs if not should_exclude_dir(d)]

        # Calculate relative path
        rel_path = os.path.relpath(root, local_root)
        if rel_path == ".":
            curr_remote_dir = remote_root
        else:
            curr_remote_dir = remote_root + "/" + rel_path.replace("\\", "/")

        ensure_remote_dir(ftp, curr_remote_dir)
        ftp.cwd(curr_remote_dir)

        for f in files:
            if should_exclude_file(f):
                total_skipped += 1
                continue

            local_file_path = os.path.join(root, f)
            try:
                with open(local_file_path, "rb") as fp:
                    ftp.storbinary(f"STOR {f}", fp)
                total_uploaded += 1
                print(f"  -> Uploaded: {os.path.join(rel_path, f)}")
            except Exception as err:
                print(f"  [!] Failed to upload {f}: {err}", file=sys.stderr)

    return total_uploaded, total_skipped


def restart_passenger(ftp: ftplib.FTP):
    """
    Touches /tmp/restart.txt to reload Passenger WSGI on cPanel.
    """
    try:
        ts = str(time.time()).encode("utf-8")
        ftp.storbinary("STOR /tmp/restart.txt", io.BytesIO(ts))
        print("[*] Successfully touched /tmp/restart.txt (Passenger WSGI reloaded)")
    except Exception as e:
        print(f"[!] Warning: Could not touch /tmp/restart.txt: {e}")


def main():
    print("=" * 60)
    print("  Surplus Backend Production FTP Deployment")
    print("=" * 60)
    print(f"Host: {FTP_HOST}")
    print(f"User: {FTP_USER}")
    print(f"Base Directory: {FTP_BASE}")
    print(f"Local Directory: {PROJECT_ROOT}")
    print("=" * 60)

    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        print("[+] Logged into FTP server successfully.")
    except Exception as e:
        print(f"[FATAL] Failed to connect or authenticate to FTP: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        uploaded, skipped = upload_directory(ftp, PROJECT_ROOT, FTP_BASE)
        print("=" * 60)
        print(f"[+] Upload complete! {uploaded} files uploaded, {skipped} files skipped.")

        # Reload Passenger WSGI
        restart_passenger(ftp)

        print("[+] Deployment completed successfully!")
    except Exception as e:
        print(f"[FATAL] Deployment failed during upload: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
