"""
INTAJECTION — Media Download Manager.
Handles file downloads with retry logic, smart naming, duplicate detection,
directory management, and progress/time tracking.
"""

import re
import time
import requests
from pathlib import Path
from PIL import Image


class DownloadManager:
    """Downloads media files with retry, deduplication, and smart naming."""

    def __init__(self, base_dir: str, target_username: str, log_callback=None):
        self.target_username = self._sanitize(target_username)
        self.base_dir = Path(base_dir) / "downloads" / self.target_username
        self.images_dir = self.base_dir / "images"
        self.reels_dir = self.base_dir / "reels"
        self.log = log_callback or print

        # Create output directories
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.reels_dir.mkdir(parents=True, exist_ok=True)

        # Statistics
        self.total_images = 0
        self.total_reels = 0
        self.failed_downloads = 0
        self.start_time = None

        # Duplicate tracking
        self.downloaded_files: set = set()
        self._load_existing_files()

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _sanitize(name: str) -> str:
        """Remove characters invalid in filenames."""
        return re.sub(r'[<>:"/\\|?*]', "_", name).strip(". ")

    def _load_existing_files(self):
        """Index already-downloaded filenames to skip duplicates."""
        for d in (self.images_dir, self.reels_dir):
            for f in d.iterdir():
                if f.is_file():
                    self.downloaded_files.add(f.name)

    # ── Timer ──────────────────────────────────────────────────

    def start_timer(self):
        self.start_time = time.time()

    def get_elapsed_time(self) -> str:
        if self.start_time is None:
            return "0s"
        elapsed = time.time() - self.start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    # ── Public download API ────────────────────────────────────

    def download_image(self, url: str, post_id: str, index: int = 0) -> bool:
        """Download a single image with smart naming."""
        filename = f"{self.target_username}_img_{post_id}_{index + 1}.jpg"
        if filename in self.downloaded_files:
            self.log(f"Skipping duplicate: {filename}")
            return True

        ok = self._download(url, self.images_dir / filename)
        if ok:
            # Convert WebP-disguised-as-jpg to real high-quality JPEG
            self._ensure_jpeg(self.images_dir / filename)
            self.total_images += 1
            self.downloaded_files.add(filename)
            self.log(f"Image saved: {filename}")
        else:
            self.failed_downloads += 1
            self.log(f"Failed: {filename}")
        return ok

    def _ensure_jpeg(self, filepath: Path):
        """If the file is actually WebP (RIFF header), convert to real JPEG."""
        try:
            with open(filepath, "rb") as f:
                header = f.read(4)
            if header == b"RIFF":  # WebP signature
                img = Image.open(filepath)
                if img.mode in ("RGBA", "P", "LA", "PA"):
                    img = img.convert("RGB")
                img.save(str(filepath), "JPEG", quality=100, optimize=True)
                img.close()
                self.log(f"    Converted WebP -> JPEG (quality 95%)")
        except Exception as exc:
            self.log(f"    Format conversion note: {str(exc)[:80]}")

    def download_reel(self, url: str, post_id: str) -> bool:
        """Download a reel video."""
        filename = f"{self.target_username}_reel_{post_id}.mp4"
        if filename in self.downloaded_files:
            self.log(f"Skipping duplicate reel: {filename}")
            return True

        ok = self._download(url, self.reels_dir / filename)
        if ok:
            self.total_reels += 1
            self.downloaded_files.add(filename)
            self.log(f"Reel saved: {filename}")
        else:
            self.failed_downloads += 1
            self.log(f"Failed reel: {filename}")
        return ok

    # ── Core download with retry ───────────────────────────────

    def _download(self, url: str, filepath: Path, retries: int = 3) -> bool:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            ),
            "Referer": "https://www.instagram.com/",
            "Accept": "*/*",
        }

        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=headers, timeout=90, stream=True)
                resp.raise_for_status()

                with open(filepath, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)

                if filepath.exists() and filepath.stat().st_size > 0:
                    return True

                filepath.unlink(missing_ok=True)

            except requests.RequestException as exc:
                wait = (2 ** attempt) * 2
                self.log(
                    f"Attempt {attempt + 1}/{retries} failed: "
                    f"{str(exc)[:80]}"
                )
                if attempt < retries - 1:
                    self.log(f"Retrying in {wait}s…")
                    time.sleep(wait)
            except Exception as exc:
                self.log(f"Unexpected error: {str(exc)[:80]}")
                break

        return False

    # ── Summary ────────────────────────────────────────────────

    def get_summary(self, total_posts: int = 0) -> str:
        elapsed = self.get_elapsed_time()
        status_text = "Completed Successfully" if self.failed_downloads == 0 else "Completed with Warnings"
        if total_posts == 0:
            total_posts = self.total_images + self.total_reels + self.failed_downloads
        return (
            "\n"
            "----------------------------------------\n"
            "DOWNLOAD SUMMARY\n"
            "----------------------------------------\n"
            f"Status           : {status_text}\n"
            f"Target Profile   : {self.target_username}\n"
            f"Total Posts      : {total_posts}\n"
            f"Images Saved     : {self.total_images}\n"
            f"Reels Saved      : {self.total_reels}\n"
            f"Time Elapsed     : {elapsed}\n"
            f"Failed / Errors  : {self.failed_downloads}\n"
            "----------------------------------------"
        )
