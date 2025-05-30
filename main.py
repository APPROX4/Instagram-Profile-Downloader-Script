import os
import time
import json
import urllib.request
import requests
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import customtkinter as ctk
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from PIL import Image
import io
import concurrent.futures
from tqdm import tqdm

# === SETTINGS ===
CHROMEDRIVER_PATH = "C:\\WebDrivers\\chromedriver.exe"  # Adjust the path if needed
DOWNLOAD_DIR = "downloads"
CREDENTIALS_FILE = "credentials.json"  # File to save login credentials
MAX_WORKERS = 10  # Number of concurrent image processing workers

# === UTILS ===
def delay(min_sec=2, max_sec=4):
    time.sleep(min_sec + (max_sec - min_sec) * 0.5)

def sanitize_filename(name):
    invalid_chars = r'<>:"/\|?*'
    return ''.join(c for c in name if c not in invalid_chars)

def save_credentials(username, password):
    credentials = {
        'username': username,
        'password': password
    }
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(credentials, f)

def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, 'r') as f:
            return json.load(f)
    return None

def get_video_url_from_logs(driver):
    """Extract video URL from network logs using the working approach"""
    logs = driver.get_log("performance")
    video_candidates = {}  # {url: transferred_size}

    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]

            # Only handle finished network loads
            if message["method"] == "Network.loadingFinished":
                req_id = message["params"]["requestId"]
                total_bytes = message["params"].get("encodedDataLength", 0)

                # Backtrack to find matching request URL
                for back_entry in logs:
                    back_msg = json.loads(back_entry["message"])["message"]
                    if back_msg["method"] == "Network.requestWillBeSent":
                        if back_msg["params"]["requestId"] == req_id:
                            url = back_msg["params"]["request"]["url"]
                            if ".mp4" in url and "fna.fbcdn.net" in url:
                                # Store both the URL and its size
                                video_candidates[url] = total_bytes
                            break

        except Exception:
            continue

    if not video_candidates:
        return None

    # Sort candidates by size in descending order to get highest quality
    sorted_candidates = sorted(video_candidates.items(), key=lambda x: x[1], reverse=True)
    
    # Get the URL with the largest size (highest quality)
    best_url = sorted_candidates[0][0]

    # Clean URL
    parsed = urlparse(best_url)
    query = parse_qs(parsed.query)
    query.pop("bytestart", None)
    query.pop("byteend", None)

    clean_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query, doseq=True),
        parsed.fragment
    ))

    return clean_url

def extract_video_url_from_page(driver):
    """Extract video URL directly from the page source"""
    try:
        # Method 1: Try to get video URL from video element
        video_elements = driver.find_elements(By.XPATH, "//video")
        for video_elem in video_elements:
            video_src = video_elem.get_attribute("src")
            if video_src and ".mp4" in video_src:
                return video_src
        
        # Method 2: Try to find video URL in page source
        page_source = driver.page_source
        mp4_urls = re.findall(r'https://[^"\']+\.mp4[^"\']*', page_source)
        if mp4_urls:
            # Filter for high-quality videos (usually the largest ones)
            filtered_urls = [url for url in mp4_urls if "fna.fbcdn.net" in url]
            if filtered_urls:
                return filtered_urls[0]
            return mp4_urls[0]
        
        # Method 3: Try to find video URL in JSON data
        json_data = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page_source)
        for data in json_data:
            try:
                json_obj = json.loads(data)
                if "video" in json_obj and "contentUrl" in json_obj["video"]:
                    return json_obj["video"]["contentUrl"]
            except:
                continue
                
        return None
    except Exception as e:
        print(f"Error extracting video URL from page: {e}")
        return None

def download_video(url, save_path):
    """Download video with proper headers and error handling"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.instagram.com/",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Range": "bytes=0-"
    }
    
    try:
        # First check if the URL is accessible and get content length
        head_response = requests.head(url, headers=headers, allow_redirects=True)
        if head_response.status_code != 200:
            print(f"URL not accessible: {head_response.status_code}")
            return False
            
        content_length = int(head_response.headers.get('content-length', 0))
        
        # Check if the video is too small (likely incomplete)
        if content_length < 100000:  # Less than 100KB is suspicious
            print(f"Video too small ({content_length} bytes), likely incomplete")
            return False
            
        # Download the video
        r = requests.get(url, headers=headers, stream=True)
        r.raise_for_status()
        
        # Get content length for progress tracking
        total_size = int(r.headers.get('content-length', 0))
        
        # Verify content length matches
        if total_size != content_length:
            print(f"Content length mismatch: {total_size} vs {content_length}")
            return False
        
        with open(save_path, "wb") as f:
            if total_size == 0:
                # No content length header
                f.write(r.content)
            else:
                # Download with progress tracking
                downloaded = 0
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        # Print progress
                        if total_size > 0:
                            percent = int(100 * downloaded / total_size)
                
                # Verify downloaded size matches expected size
                if downloaded != total_size:
                    print(f"Download size mismatch: {downloaded} vs {total_size}")
                    return False
                
        return True
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False

def process_image(image_data, save_path):
    """Process and convert image to proper format"""
    try:
        # Create image from bytes
        img = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if needed (for PNG with transparency)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Save as JPEG with quality 100
        img.save(save_path, 'JPEG', quality=100)
        return True
    except Exception as e:
        print(f"Error processing image: {e}")
        return False

def download_and_process_image(url, save_path):
    """Download and process image with proper format handling"""
    try:
        # Download image with proper headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.instagram.com/",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        
        # Process and save image
        if process_image(response.content, save_path):
            return True
        return False
    except Exception as e:
        print(f"Error downloading image: {e}")
        return False

def batch_process_images(image_tasks):
    """Process multiple images concurrently"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for url, save_path in image_tasks:
            futures.append(executor.submit(download_and_process_image, url, save_path))
        
        # Wait for all tasks to complete
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Processing images"):
            try:
                future.result()
            except Exception as e:
                print(f"Error in image processing task: {e}")

class InstaDownloader(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Instagram Profile Downloader")
        self.geometry("800x500")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color="#232323")

        # --- Fonts ---
        FONT_HEADER = ("Segoe UI", 20, "bold", "italic")
        FONT_LABEL = ("Segoe UI", 13)
        FONT_INPUT = ("Segoe UI", 13)
        FONT_BUTTON = ("Segoe UI", 14, "bold")
        FONT_LOG = ("Consolas", 11)
        FONT_FOOTER = ("Segoe UI", 14)

        # --- Header Bar ---
        self.header = ctk.CTkFrame(self, fg_color="#ffffff", height=55)
        self.header.pack(fill="x", side="top", padx=0, pady=(0,0))
        self.header.grid_propagate(False)
        self.header_label = ctk.CTkLabel(self.header, text="INSTAGRAM PROFILE DOWNLOADER", font=FONT_HEADER, text_color="#111", anchor="center")
        self.header_label.place(relx=0.5, rely=0.5, anchor="center")

        # --- Main Content ---
        self.main = ctk.CTkFrame(self, fg_color="#232323", corner_radius=20)
        self.main.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.main.grid_columnconfigure(0, weight=0)
        self.main.grid_columnconfigure(1, weight=1)
        self.main.grid_rowconfigure(0, weight=1)

        # --- Left Column ---
        self.left = ctk.CTkFrame(self.main, fg_color="#232323")
        self.left.grid(row=0, column=0, sticky="nsew", padx=(30,10), pady=(20,10))
        self.left.grid_columnconfigure(0, weight=1)

        self.target = ctk.StringVar()
        self.username = ctk.StringVar()
        self.password = ctk.StringVar()
        self.remember_me = ctk.BooleanVar()

        ctk.CTkLabel(self.left, text="Target Username / URL of Profile", font=FONT_LABEL, text_color="#fff", anchor="w").grid(row=0, column=0, sticky="w", pady=(0,2))
        self.target_entry = ctk.CTkEntry(self.left, textvariable=self.target, font=FONT_INPUT, width=270, height=32, fg_color="#dddddd", text_color="#111", border_width=0, corner_radius=10)
        self.target_entry.grid(row=1, column=0, sticky="ew", pady=(0,14))

        ctk.CTkLabel(self.left, text="Your Username", font=FONT_LABEL, text_color="#fff", anchor="w").grid(row=2, column=0, sticky="w", pady=(0,2))
        self.username_entry = ctk.CTkEntry(self.left, textvariable=self.username, font=FONT_INPUT, width=220, height=32, fg_color="#dddddd", text_color="#111", border_width=0, corner_radius=10)
        self.username_entry.grid(row=3, column=0, sticky="ew", pady=(0,14))

        ctk.CTkLabel(self.left, text="Your Password", font=FONT_LABEL, text_color="#fff", anchor="w").grid(row=4, column=0, sticky="w", pady=(0,2))
        self.password_entry = ctk.CTkEntry(self.left, textvariable=self.password, font=FONT_INPUT, width=220, height=32, fg_color="#dddddd", text_color="#111", border_width=0, corner_radius=10, show="*")
        self.password_entry.grid(row=5, column=0, sticky="ew", pady=(0,14))

        self.remember_cb = ctk.CTkCheckBox(self.left, text="Remember me", variable=self.remember_me, font=FONT_LABEL, text_color="#fff", fg_color="#dddddd", border_color="#888", hover_color="#bbb", corner_radius=6)
        self.remember_cb.grid(row=6, column=0, sticky="w", pady=(0,18))

        self.download_btn = ctk.CTkButton(self.left, text="DOWNLOAD", font=FONT_BUTTON, fg_color="#dddddd", text_color="#222", hover_color="#bbbbbb", corner_radius=10, width=160, height=40, command=self.start_download)
        self.download_btn.grid(row=7, column=0, pady=(10,0))

        # --- Right Column ---
        self.right = ctk.CTkFrame(self.main, fg_color="#232323")
        self.right.grid(row=0, column=1, sticky="nsew", padx=(10,10), pady=(20,10))
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.right, text="Log", font=FONT_LABEL, text_color="#fff", anchor="w").grid(row=0, column=0, sticky="w", pady=(0,2))
        self.log_box = ctk.CTkTextbox(self.right, font=FONT_LOG, fg_color="#dddddd", text_color="#222", width=370, height=320, corner_radius=10, border_width=0)
        self.log_box.grid(row=1, column=0, sticky="nsew")
        self.log_box.configure(state="disabled")

        self.copy_log_btn = ctk.CTkButton(self.right, text="COPY LOG", font=("Segoe UI", 10), fg_color="#dddddd", text_color="#222", hover_color="#bbbbbb", corner_radius=8, width=80, height=28, command=self.copy_log)
        self.copy_log_btn.grid(row=2, column=0, sticky="e", pady=(6,0))

        # --- Footer ---
        self.footer = ctk.CTkFrame(self, fg_color="#232323", height=30)
        self.footer.pack(fill="x", side="bottom")
        ctk.CTkLabel(self.footer, text="Script By APPROX", font=FONT_FOOTER, text_color="#ccc", anchor="w").pack(side="left", padx=18, pady=2)

        # Load saved credentials if available
        credentials = load_credentials()
        if credentials:
            self.username.set(credentials['username'])
            self.password.set(credentials['password'])
            self.remember_me.set(True)

    def log(self, msg, level="info"):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.update()

    def copy_log(self):
        self.log_box.configure(state="normal")
        self.clipboard_clear()
        self.clipboard_append(self.log_box.get("1.0", "end").strip())
        self.log_box.configure(state="disabled")
        self.log("Log copied to clipboard.", level="success")

    def start_download(self):
        try:
            self.download_profile()
        except Exception as e:
            self.log(f"Error: {e}", level="error")
            ctk.messagebox.showerror("Error", str(e))

    def collect_all_posts(self, driver, profile_url):
        import time
        self.log("Collecting all post URLs...")
        post_links = set()
        reel_links = set()
        last_height = driver.execute_script("return document.body.scrollHeight")
        last_new_post_time = time.time()
        timeout = 15  # seconds
        last_reported = (0, 0)
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            delay(2, 3)
            links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/') or contains(@href, '/reel/')]")
            prev_count = len(post_links) + len(reel_links)
            for link in links:
                try:
                    href = link.get_attribute("href")
                    if href:
                        if "/p/" in href:
                            post_links.add(href)
                        elif "/reel/" in href:
                            reel_links.add(href)
                except StaleElementReferenceException:
                    continue
            new_count = len(post_links) + len(reel_links)
            if new_count > prev_count:
                last_new_post_time = time.time()  # Reset timer if new post found
            new_height = driver.execute_script("return document.body.scrollHeight")
            # Only log if new posts/reels found or every 5s
            if (len(post_links), len(reel_links)) != last_reported:
                self.log(f"Found {len(post_links)} posts and {len(reel_links)} reels and keep looking...")
                last_reported = (len(post_links), len(reel_links))
            if time.time() - last_new_post_time > timeout:
                self.log("Reached the bottom of the page.")
                break
            if new_height == last_height:
                time.sleep(1)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    self.log("Reached the bottom of the page.")
                    break
            last_height = new_height
        return list(reel_links), list(post_links)

    def get_all_media_from_carousel(self, driver):
        import time
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        media = []
        seen_urls = set()
        max_carousel_attempts = 100
        carousel_attempts = 0
        last_media_count = 0
        last_new_media_time = time.time()
        timeout = 8
        time.sleep(2)
        while carousel_attempts < max_carousel_attempts:
            imgs = driver.find_elements(By.XPATH, "//article//img")
            for img in imgs:
                try:
                    src = img.get_attribute("src")
                    if src and "150x150" not in src and src not in seen_urls:
                        media.append({"url": src, "type": "image"})
                        seen_urls.add(src)
                        last_new_media_time = time.time()
                except Exception:
                    continue

            logs = driver.get_log("performance")
            video_candidates = {}
            for entry in logs:
                try:
                    message = json.loads(entry["message"])["message"]
                    if message["method"] == "Network.loadingFinished":
                        req_id = message["params"]["requestId"]
                        total_bytes = message["params"].get("encodedDataLength", 0)
                        for back_entry in logs:
                            back_msg = json.loads(back_entry["message"])["message"]
                            if back_msg["method"] == "Network.requestWillBeSent":
                                if back_msg["params"]["requestId"] == req_id:
                                    url = back_msg["params"]["request"]["url"]
                                    if ".mp4" in url and "fna.fbcdn.net" in url and url not in seen_urls:
                                        video_candidates[url] = total_bytes
                        break
                except Exception:
                    continue
            if video_candidates:
                sorted_candidates = sorted(video_candidates.items(), key=lambda x: x[1], reverse=True)
                best_url = sorted_candidates[0][0]
                parsed = urlparse(best_url)
                query = parse_qs(parsed.query)
                query.pop("bytestart", None)
                query.pop("byteend", None)
                clean_url = urlunparse((
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    urlencode(query, doseq=True),
                    parsed.fragment
                ))
                if clean_url not in seen_urls:
                    media.append({"url": clean_url, "type": "video"})
                    seen_urls.add(clean_url)
                    last_new_media_time = time.time()
            try:
                next_btn = driver.find_element(By.XPATH, "//button[@aria-label='Next']")
                next_btn.click()
                time.sleep(1)
                carousel_attempts += 1
            except NoSuchElementException:
                break
            except Exception as e:
                self.log(f"Error navigating carousel: {e}", level="warning")
                try:
                    time.sleep(1)
                    next_btn = driver.find_element(By.XPATH, "//button[@aria-label='Next']")
                    next_btn.click()
                    time.sleep(1)
                except:
                    break
            if time.time() - last_new_media_time > timeout:
                self.log(f"No new media found for {timeout} seconds. Stopping carousel swipe.", level="warning")
                break
        self.log(f"Found {len(media)} total media in carousel (images + videos)", level="success")
        return media

    def download_profile(self):
        import time
        start_time = time.time()
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--disable-save-password-bubble")
        options.add_argument("--disable-translate")
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)
        driver.execute_cdp_cmd("Network.enable", {})

        try:
            driver.get("https://www.instagram.com/")
            delay()

            if self.remember_me.get():
                self.log("Logging in...")
                delay()
                driver.find_element(By.NAME, "username").send_keys(self.username.get())
                driver.find_element(By.NAME, "password").send_keys(self.password.get())
                driver.find_element(By.NAME, "password").send_keys(Keys.ENTER)
                delay(8, 9)
                self.log("Login successful.")

            # Navigate to profile
            target = self.target.get().strip()
            if target.startswith("http"):
                profile_url = target
            else:
                profile_url = f"https://www.instagram.com/{target}/"

            driver.get(profile_url)
            delay(4, 6)

            profile_name = profile_url.strip("/").split("/")[-1]
            save_folder = os.path.join(DOWNLOAD_DIR, profile_name)
            os.makedirs(save_folder, exist_ok=True)

            # Collect all post links including reels
            reel_links, post_links = self.collect_all_posts(driver, profile_url)
            total_links = len(reel_links) + len(post_links)
            self.log(f"Total found: {len(reel_links)} reels and {len(post_links)} posts")
            
            # First download all reels
            self.log("\n=== DOWNLOADING REELS ===")
            for index, reel_url in enumerate(reel_links):
                # Clear logs before processing each post
                driver.get_log("performance")
                driver.get(reel_url)
                self.log(f"[Reel {index+1}/{len(reel_links)}] {reel_url}")
                self.log("Waiting for video to load...")
                time.sleep(5)  # Wait for video to load

                # Try to play the video to trigger all qualities
                try:
                    play_button = driver.find_element(By.XPATH, "//button[@aria-label='Play']")
                    play_button.click()
                    time.sleep(2)
                except:
                    pass

                # Wait a bit more to ensure all video qualities are loaded
                time.sleep(3)

                # Get logs after waiting
                logs = driver.get_log("performance")
                video_candidates = {}

                for entry in logs:
                    try:
                        message = json.loads(entry["message"])["message"]
                        if message["method"] == "Network.loadingFinished":
                            req_id = message["params"]["requestId"]
                            total_bytes = message["params"].get("encodedDataLength", 0)
                            for back_entry in logs:
                                back_msg = json.loads(back_entry["message"])["message"]
                                if back_msg["method"] == "Network.requestWillBeSent":
                                    if back_msg["params"]["requestId"] == req_id:
                                        url = back_msg["params"]["request"]["url"]
                                        if ".mp4" in url and "fna.fbcdn.net" in url:
                                            video_candidates[url] = total_bytes
                                        break
                    except Exception:
                        continue

                # If no video found, try refreshing and repeat (up to 2-3 times)
                retries = 0
                while not video_candidates and retries < 2:
                    self.log("No video found, refreshing and retrying...")
                    driver.refresh()
                    time.sleep(5)
                    try:
                        play_button = driver.find_element(By.XPATH, "//button[@aria-label='Play']")
                        play_button.click()
                        time.sleep(2)
                    except:
                        pass
                    time.sleep(3)
                    logs = driver.get_log("performance")
                    for entry in logs:
                        try:
                            message = json.loads(entry["message"])["message"]
                            if message["method"] == "Network.loadingFinished":
                                req_id = message["params"]["requestId"]
                                total_bytes = message["params"].get("encodedDataLength", 0)
                                for back_entry in logs:
                                    back_msg = json.loads(back_entry["message"])["message"]
                                    if back_msg["method"] == "Network.requestWillBeSent":
                                        if back_msg["params"]["requestId"] == req_id:
                                            url = back_msg["params"]["request"]["url"]
                                            if ".mp4" in url and "fna.fbcdn.net" in url:
                                                video_candidates[url] = total_bytes
                                            break
                        except Exception:
                            continue
                    retries += 1

                if video_candidates:
                    # Always pick the largest file
                    sorted_candidates = sorted(video_candidates.items(), key=lambda x: x[1], reverse=True)
                    best_url = sorted_candidates[0][0]
                    # Clean URL
                    parsed = urlparse(best_url)
                    query = parse_qs(parsed.query)
                    query.pop("bytestart", None)
                    query.pop("byteend", None)
                    video_url = urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        urlencode(query, doseq=True),
                        parsed.fragment
                    ))
                    filename = f"reel_{index+1}.mp4"
                    save_path = os.path.join(save_folder, filename)
                    self.log("Found and Downloading..")
                    success = False
                    max_retries = 3
                    retry_count = 0
                    while not success and retry_count < max_retries:
                        if download_video(video_url, save_path):
                            if os.path.getsize(save_path) > 100000:  # More than 100KB
                                success = True
                                self.log(f"Saved reel: {filename}")
                            else:
                                self.log("Downloaded file too small, retrying...")
                                os.remove(save_path)
                        else:
                            self.log(f"Download attempt {retry_count + 1} failed, trying with different headers...")
                            headers = {
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                "Referer": "https://www.instagram.com/",
                                "Accept": "*/*",
                                "Accept-Language": "en-US,en;q=0.9",
                                "Connection": "keep-alive"
                            }
                            try:
                                r = requests.get(video_url, headers=headers, stream=True)
                                r.raise_for_status()
                                with open(save_path, "wb") as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        if chunk:
                                            f.write(chunk)
                                if os.path.getsize(save_path) > 100000:
                                    success = True
                                    self.log(f"Saved reel: {filename}")
                                else:
                                    self.log("Downloaded file too small, retrying...")
                                    os.remove(save_path)
                            except Exception as e:
                                self.log(f"Download attempt {retry_count + 1} failed: {e}")
                        retry_count += 1
                        if not success and retry_count < max_retries:
                            self.log(f"Retrying download (attempt {retry_count + 1}/{max_retries})...")
                            time.sleep(2)
                    if not success:
                        self.log(f"No video found for this reel.")
                else:
                    self.log("No video found for this reel.")
                

            # Then download all regular posts
            self.log("\n=== DOWNLOADING REGULAR IMAGE + REELS POSTS ===")
            for index, post_url in enumerate(post_links):
                driver.get(post_url)
                delay(2, 3)
                self.log(f"\n[Post {index+1}/{len(post_links)}] {post_url}")
                
                # Clear logs before processing each post
                driver.get_log("performance")

                # First check for video content
                has_video = False
                video_url = None
                
                # Wait for content to load
                time.sleep(3)
                
                # Check for video element
                if driver.find_elements(By.XPATH, "//video"):
                    has_video = True
                    self.log("Detected video in post, extracting video URL...")
                    
                    # Wait for video to load
                    self.log("Waiting for video to load...")
                    time.sleep(5)
                    
                    # Try to find and click the play button if it exists
                    try:
                        play_button = driver.find_element(By.XPATH, "//button[@aria-label='Play']")
                        play_button.click()
                        time.sleep(2)
                    except:
                        pass
                    
                    # Get logs after waiting
                    logs = driver.get_log("performance")
                    
                    # Parse logs for .mp4 responses
                    video_candidates = {}

                    for entry in logs:
                        try:
                            message = json.loads(entry["message"])["message"]
                            if message["method"] == "Network.loadingFinished":
                                req_id = message["params"]["requestId"]
                                total_bytes = message["params"].get("encodedDataLength", 0)
                                for back_entry in logs:
                                    back_msg = json.loads(back_entry["message"])["message"]
                                    if back_msg["method"] == "Network.requestWillBeSent":
                                        if back_msg["params"]["requestId"] == req_id:
                                            url = back_msg["params"]["request"]["url"]
                                            if ".mp4" in url and "fna.fbcdn.net" in url:
                                                video_candidates[url] = total_bytes
                                            break
                        except Exception:
                            continue

                    if video_candidates:
                        # Sort candidates by size in descending order
                        sorted_candidates = sorted(video_candidates.items(), key=lambda x: x[1], reverse=True)
                        
                        # Get the URL with the largest size
                        best_url = sorted_candidates[0][0]
                        
                        # Clean URL
                        parsed = urlparse(best_url)
                        query = parse_qs(parsed.query)
                        query.pop("bytestart", None)
                        query.pop("byteend", None)
                        
                        video_url = urlunparse((
                            parsed.scheme,
                            parsed.netloc,
                            parsed.path,
                            parsed.params,
                            urlencode(query, doseq=True),
                            parsed.fragment
                        ))
                    else:
                        # Try alternative methods if no video found in logs
                        video_url = extract_video_url_from_page(driver)

                # Download video if found
                if video_url:
                    filename = f"post_video_{index+1}.mp4"
                    save_path = os.path.join(save_folder, filename)
                    if not os.path.exists(save_path):
                        self.log(f"Downloading video from: {video_url[:50]}...")
                        
                        success = False
                        max_retries = 3
                        retry_count = 0
                        
                        while not success and retry_count < max_retries:
                            if download_video(video_url, save_path):
                                if os.path.getsize(save_path) > 100000:
                                    success = True
                                    self.log(f"Saved video: {filename}")
                                else:
                                    self.log("Downloaded file too small, retrying...")
                                    os.remove(save_path)
                            else:
                                self.log(f"Download attempt {retry_count + 1} failed, trying with different headers...")
                                headers = {
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                                    "Referer": "https://www.instagram.com/",
                                    "Accept": "*/*",
                                    "Accept-Language": "en-US,en;q=0.9",
                                    "Connection": "keep-alive"
                                }
                                
                                try:
                                    r = requests.get(video_url, headers=headers, stream=True)
                                    r.raise_for_status()
                                    
                                    with open(save_path, "wb") as f:
                                        for chunk in r.iter_content(chunk_size=8192):
                                            if chunk:
                                                f.write(chunk)
                                    
                                    if os.path.getsize(save_path) > 100000:
                                        success = True
                                        self.log(f"Saved video: {filename}")
                                    else:
                                        self.log("Downloaded file too small, retrying...")
                                        os.remove(save_path)
                                except Exception as e:
                                    self.log(f"Download attempt {retry_count + 1} failed: {e}")
                            
                            retry_count += 1
                            if not success and retry_count < max_retries:
                                self.log(f"Retrying download (attempt {retry_count + 1}/{max_retries})...")
                                time.sleep(2)
                        
                        if not success:
                            self.log(f"Failed to download video after {max_retries} attempts: {filename}")
                    else:
                        self.log(f"Skipped (exists): {filename}")

                # Get all images from the post (including carousel)
                media_urls = self.get_all_media_from_carousel(driver)
                self.log(f"Found {len(media_urls)} total media in carousel (images + videos)")
                img_count = sum(1 for m in media_urls if m.get("type") == "image")
                vid_count = sum(1 for m in media_urls if m.get("type") == "video")
                self.log(f"Found {img_count} images in this post")
                self.log(f"Found {vid_count} reels in this post")

                # Prepare image download tasks (only for images)
                image_tasks = []
                for img_index, media in enumerate(media_urls):
                    if isinstance(media, dict) and media.get("type") == "image":
                        url = media.get("url")
                        filename = f"post_{index+1}_img_{img_index+1}.jpg"
                        save_path = os.path.join(save_folder, filename)
                        if not os.path.exists(save_path):
                            image_tasks.append((url, save_path))
                            self.log(f"Queued: {filename}")
                        else:
                            self.log(f"Skipped (exists): {filename}")

                # Process images in batches
                if image_tasks:
                    self.log(f"Processing {len(image_tasks)} images...")
                    batch_process_images(image_tasks)
                    self.log("Image processing complete.")

            self.log("✅ Download Complete.")
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            self.log(f"\nDownload Complect (total time need:{mins:02d}:{secs:02d} min)")

        except Exception as e:
            self.log(f"Error during download: {e}", level="error")
            raise e
        finally:
            driver.quit()

if __name__ == "__main__":
    app = InstaDownloader()
    app.mainloop() 
