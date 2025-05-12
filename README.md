# 📸 Instagram Profile Downloader

A powerful Python-based tool to download all media content from Instagram profiles, including posts, reels, and carousel images.

![Python](https://img.shields.io/badge/Python-3.7%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

## ⚠️ Important Disclaimer

This tool is for educational purposes only. Using this script may result in:
- Soft bans from Instagram
- Temporary account restrictions
- IP bans
- Login issues (even with correct credentials)
- Rate limiting

Use at your own risk and responsibly.

## ✨ Features

- 📥 Download all posts from any Instagram profile
- 🎥 Download reels and videos
- 🖼️ Download carousel images
- 🔐 Support for private profiles (with login)
- 💾 Remember login credentials (optional)
- 📊 Progress tracking
- 🎯 High-quality media downloads
- 🔄 Automatic retry mechanism for failed downloads
- 🎨 Modern GUI interface

## 🚀 Upcoming Features

- [ ] Highlights download support
- [ ] Stories download support
- [ ] Better error handling
- [ ] Download speed improvements
- [ ] Multiple profile batch download

## 📋 Prerequisites

Before using this script, ensure you have the following installed:

1. Python 3.7 or higher
2. Chrome browser
3. ChromeDriver (matching your Chrome version)

## 📦 Required Python Packages

```bash
pip install -r requirements.txt
```

Required packages:
- selenium
- requests
- tkinter
- urllib3

## 🔧 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/instagram-profile-downloader.git
cd instagram-profile-downloader
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Download ChromeDriver:
   - Visit [ChromeDriver downloads](https://sites.google.com/chromium.org/driver/)
   - Download the version matching your Chrome browser
   - Place it in `C:\WebDrivers\chromedriver.exe` or update the path in the script

## 💻 Usage

1. Run the script:
```bash
python main.py
```

2. Enter the target Instagram profile username or URL
3. (Optional) Enable login for private profiles
4. Click "Start Download"

## 📁 Output

All downloaded media will be saved in the `downloads` folder, organized by profile name:
- Posts: `post_X_img_Y.jpg`
- Videos: `post_video_X.mp4`
- Reels: `reel_X.mp4`
- Reel thumbnails: `reel_thumb_X.jpg`

## ⚠️ Known Limitations

- Slow download speed for large profiles
- No support for highlights (coming soon)
- May trigger Instagram's anti-bot measures
- Requires manual ChromeDriver updates
- GUI may freeze during large downloads

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Warning

This script is 80% AI-generated and 20% human-developed. Use responsibly and at your own risk. The developers are not responsible for any account restrictions or bans that may occur from using this tool.

## 🙏 Acknowledgments

- Selenium WebDriver
- Python community
- Instagram (for the platform)

---

Made with ❤️ and 🤖 