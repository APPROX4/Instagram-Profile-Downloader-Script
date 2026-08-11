"""
INSTAJECTION — Instagram Image & Reels Downloader
Entry point — launches the modern desktop GUI.

Usage:
    python main.py

Requirements:
    pip install -r requirements.txt
    Firefox browser must be installed.
    geckodriver will be auto-downloaded on first run.
"""

import sys
import os

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure the script's own directory is on the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui_app import launch


def main():
    """Bootstrap and run INSTAJECTION."""
    print("Starting INSTAJECTION...")
    launch()


if __name__ == "__main__":
    main()
