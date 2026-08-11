<h1 align="center">INSTAJECTION 2.0.1</h1>
<p align="center">
  <em>Instagram Profile Downloader — Images & Reels</em>
</p>

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.13%2B-blue?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/License-GPL3.0-green?style=for-the-badge&logo=gnu&logoColor=white"/>
  <img src="https://img.shields.io/badge/Selenium-Firefox-FF7139?style=for-the-badge&logo=selenium&logoColor=white" />
  <img src="https://img.shields.io/badge/Last Check-11 AUG 2026-lightblue?style=for-the-badge&logo=cachet&logoColor=white"/>
</div>

<p align="center">
  <img src="logo/instajection.png" alt="INSTAJECTION" width="1800" />
</p>

---
<div align="center">Downloads all images and reels from any public Instagram profile. Features a modern dark-themed GUI, encrypted credential storage, smart duplicate detection.</div>
<p></p>
<p align="center">
  <a href="https://postimg.cc/HrVgz0Tn">
    <img src="https://i.postimg.cc/NjxjgbV6/image.png" alt="Capp.png"/>
  </a>
</p>

## ⚠️ Important Disclaimer</div>

<div style="background-color: #2d2d2d; padding: 40px; border-radius: 40px; margin: 40px 0;">
  <p style="color: #ff6b6b; font-weight: bold;">⚠️ This tool is for educational purposes only.</p>
  <p style="color: #ffffff;">Using this script may result in:</p>
  <ul style="color: #ffffff;">
    <li>Soft bans from Instagram</li>
    <li>Temporary account restrictions</li>
    <li>IP bans</li>
    <li>Login issues (even with correct password or id)</li>
    <li>Rate limiting</li>
  </ul>
  <p style="color: #ff6b6b;">Use at your own risk and responsibly.</p>
</div>

---

## Features

- **Download All Content** — Images, carousel posts, and reels from profile
- **Modern Dark GUI** — Sleek CustomTkinter interface with real-time log
- **Duplicate Detection** — Skips already-downloaded files automatically
- **Encrypted Credentials** — Login details stored securely with Fernet encryption
- **Remember Me** — Save credentials for quick re-login
- **Download Order** — Choose images-first or reels-first
- **Retry Logic** — Failed downloads retry with exponential backoff

---

## Quick Start (EXE)

> **No Python needed** — just download and run.

1. **[🚀 Click Here to Download the Latest .exe](https://github.com/APPROX4/Instagram-Profile-Downloader-Script/releases/tag/NSTAJECTION-2.0.1)**
2. Make sure **Firefox** is installed on your PC
3. Double-click the `.exe` and start downloading

---
## Quick Start (Python)

### Prerequisites

- Python 3.10+
- Firefox browser installed

### Installation

```bash
git clone https://github.com/APPROX4/Instagram-Profile-Downloader-Script.git
cd Instajection
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

---

## How to Use

1. Enter your **Instagram username/email** and **password**
2. Check **Remember** to save credentials for next time
3. Enter the **target username** or profile URL
4. Toggle **Image First / Reels First** based on preference
5. Click **Start Download**
6. Watch the log panel for real-time progress
7. Files are saved to `downloads/<username>/images/` and `downloads/<username>/reels/`

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `selenium` | Browser automation (Firefox WebDriver) |
| `webdriver-manager` | Auto-downloads geckodriver |
| `customtkinter` | Modern dark-themed GUI |
| `Pillow` | Image processing (WebP → JPEG) |
| `requests` | HTTP downloads |
| `cryptography` | Encrypted credential storage |

---
## Requirements

- **Windows 10/11**
- **Firefox browser** must be installed
- Geckodriver is downloaded automatically on first run

---

## ⚠️ Known Limitations

<div style="background-color: #2d2d2d; padding: 20px; border-radius: 10px; margin: 20px 0;">
  <ul style="color: #ffffff;">
    <li>Slow download speed for large profiles</li>
    <li>No support for highlights (coming soon)</li>
    <li>May trigger Instagram's anti-bot measures</li>
    <li>Requires manual ChromeDriver updates</li>
    <li>GUI may freeze during large downloads</li>
  </ul>
</div>

## License

This project is open source. Feel free to fork and modify.

---

<div align="center">
  <div style="background-color: #2d2d2d; padding: 20px; border-radius: 10px; margin: 20px 0;">
  <p style="color: #ff6b6b;">This script is 80% AI-generated and 20% My Brain.</p>
<h2 align="center">APPROX</h2>
</div>

