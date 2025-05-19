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

# === SETTINGS ===
CHROMEDRIVER_PATH = "C:\\WebDrivers\\chromedriver.exe"  # Adjust the path if needed
DOWNLOAD_DIR = "downloads"
CREDENTIALS_FILE = "credentials.json"  # File to save login credentials

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
                            print(f"\rDownloading: {percent}%", end="")
                print("\rDownload complete!                ")
                
                # Verify downloaded size matches expected size
                if downloaded != total_size:
                    print(f"Download size mismatch: {downloaded} vs {total_size}")
                    return False
                
        return True
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False

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

    def log(self, msg):
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
        self.log("Log copied to clipboard.")

    def start_download(self):
        try:
            self.download_profile()
        except Exception as e:
            self.log(f"Error: {e}")
            ctk.messagebox.showerror("Error", str(e))

    def collect_all_posts(self, driver, profile_url):
        """collect all posts including reels"""
        self.log("Collecting all post URLs...")
        post_links = set()
        reel_links = set()
        scroll_attempts = 0
        max_scroll_attempts = 30
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        # First collect regular posts
        while scroll_attempts < max_scroll_attempts:
            # Scroll to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            delay(2, 3)
            
            # Get all links
            links = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/') or contains(@href, '/reel/')]")
            
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
            
            # Check if we've reached the bottom
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
                last_height = new_height
                
            self.log(f"Found {len(post_links)} posts and {len(reel_links)} reels so far...")
            
        # Return separate lists for reels and posts
        return list(reel_links), list(post_links)

    def get_all_images_from_carousel(self, driver):
        """Get all images from a carousel post"""
        media_urls = set()
        visited_urls = set()  # Track visited image URLs instead of button IDs
        max_carousel_attempts = 100  # Increased significantly to handle posts with many images
        carousel_attempts = 0
        
        # Wait for initial images to load
        time.sleep(3)
        
        # First get all images from the current view
        imgs = driver.find_elements(By.XPATH, "//article//img")
        for img in imgs:
            try:
                src = img.get_attribute("src")
                if src and "150x150" not in src:  # Skip profile pics
                    media_urls.add(src)
                    visited_urls.add(src)
            except StaleElementReferenceException:
                continue
        
        # Then try to navigate through the carousel
        while carousel_attempts < max_carousel_attempts:
            try:
                # Look for the next button
                next_btn = driver.find_element(By.XPATH, "//button[@aria-label='Next']")
                
                # Click the next button
                next_btn.click()
                
                # Wait longer for new images to load
                time.sleep(3)
                
                # Get images from the new view
                imgs = driver.find_elements(By.XPATH, "//article//img")
                new_images_found = False
                
                for img in imgs:
                    try:
                        src = img.get_attribute("src")
                        if src and "150x150" not in src and src not in visited_urls:  # Skip profile pics and already visited URLs
                            media_urls.add(src)
                            visited_urls.add(src)
                            new_images_found = True
                    except StaleElementReferenceException:
                        continue
                
                # If no new images were found, we've probably reached the end
                if not new_images_found:
                    # Double check by trying one more time with a longer wait
                    time.sleep(2)
                    imgs = driver.find_elements(By.XPATH, "//article//img")
                    new_images_found = False
                    for img in imgs:
                        try:
                            src = img.get_attribute("src")
                            if src and "150x150" not in src and src not in visited_urls:
                                media_urls.add(src)
                                visited_urls.add(src)
                                new_images_found = True
                        except StaleElementReferenceException:
                            continue
                    
                    if not new_images_found:
                        break
                
                carousel_attempts += 1
                
            except NoSuchElementException:
                # No more next button, we're done
                break
            except Exception as e:
                self.log(f"Error navigating carousel: {e}")
                # Try one more time with a longer wait
                try:
                    time.sleep(3)
                    next_btn = driver.find_element(By.XPATH, "//button[@aria-label='Next']")
                    next_btn.click()
                    time.sleep(3)
                except:
                    break
        
        self.log(f"Found {len(media_urls)} total images in carousel")
        return media_urls

    def download_profile(self):
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
            self.log("=== DOWNLOADING REELS ===")
            for index, reel_url in enumerate(reel_links):
                # Clear logs before processing each post
                driver.get_log("performance")
                
                # Navigate to the reel
                driver.get(reel_url)
                self.log(f"[Reel {index+1}/{len(reel_links)}] {reel_url}")
                
                # Wait for video to load
                self.log("Waiting for video to load...")
                time.sleep(5)  # Increased wait time to ensure video loads
                
                # Try to find and click the play button if it exists
                try:
                    play_button = driver.find_element(By.XPATH, "//button[@aria-label='Play']")
                    play_button.click()
                    time.sleep(2)  # Wait for video to start playing
                except:
                    pass  # No play button found, continue
                
                # Get logs after waiting
                logs = driver.get_log("performance")
                
                # Parse logs for .mp4 responses
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

                # If no video found in logs, try refreshing the page and waiting again
                if not video_candidates:
                    self.log("No video found in first attempt, refreshing page...")
                    driver.refresh()
                    time.sleep(5)  # Wait for page to reload
                    
                    # Try to find and click the play button if it exists
                    try:
                        play_button = driver.find_element(By.XPATH, "//button[@aria-label='Play']")
                        play_button.click()
                        time.sleep(2)  # Wait for video to start playing
                    except:
                        pass  # No play button found, continue
                    
                    # Get logs again
                    logs = driver.get_log("performance")
                    
                    # Parse logs for .mp4 responses again
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
                    self.log("No suitable .mp4 file found in network logs, trying alternative methods...")
                    # Try alternative methods
                    video_url = extract_video_url_from_page(driver)
                else:
                    # Sort candidates by size in descending order to get highest quality
                    sorted_candidates = sorted(video_candidates.items(), key=lambda x: x[1], reverse=True)
                    
                    # Log all found video URLs and their sizes
                    self.log(f"Found {len(sorted_candidates)} video candidates:")
                    for url, size in sorted_candidates[:3]:  # Show top 3 candidates
                        self.log(f"Size: {size/1024/1024:.2f}MB - URL: {url[:50]}...")
                    
                    # Get the URL with the largest size (highest quality)
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
                
                # Download the video if we found a URL
                if video_url:
                    filename = f"reel_{index+1}.mp4"
                    save_path = os.path.join(save_folder, filename)
                    if not os.path.exists(save_path):
                        self.log(f"Downloading video from: {video_url[:50]}...")
                        
                        # Try downloading with different headers if needed
                        success = False
                        max_retries = 3
                        retry_count = 0
                        
                        while not success and retry_count < max_retries:
                            # First try with standard headers
                            if download_video(video_url, save_path):
                                # Verify the downloaded file size
                                if os.path.getsize(save_path) > 100000:  # More than 100KB
                                    success = True
                                    self.log(f"Saved reel: {filename}")
                                else:
                                    self.log("Downloaded file too small, retrying...")
                                    os.remove(save_path)  # Delete the small file
                            else:
                                # Try with different headers
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
                                    
                                    # Verify the downloaded file size
                                    if os.path.getsize(save_path) > 100000:  # More than 100KB
                                        success = True
                                        self.log(f"Saved reel: {filename}")
                                    else:
                                        self.log("Downloaded file too small, retrying...")
                                        os.remove(save_path)  # Delete the small file
                                except Exception as e:
                                    self.log(f"Download attempt {retry_count + 1} failed: {e}")
                            
                            retry_count += 1
                            if not success and retry_count < max_retries:
                                self.log(f"Retrying download (attempt {retry_count + 1}/{max_retries})...")
                                time.sleep(2)  # Wait before retrying
                        
                        if not success:
                            self.log(f"Failed to download reel after {max_retries} attempts: {filename}")
                    else:
                        self.log(f"Skipped (exists): {filename}")
                else:
                    self.log("Could not find video URL using any method")
                
                # Also download thumbnail image if available
                try:
                    imgs = driver.find_elements(By.XPATH, "//article//img")
                    for img in imgs:
                        src = img.get_attribute("src")
                        if src and "150x150" not in src:  # Skip profile pics
                            filename = f"reel_thumb_{index+1}.jpg"
                            save_path = os.path.join(save_folder, filename)
                            if not os.path.exists(save_path):
                                urllib.request.urlretrieve(src, save_path)
                                self.log(f"Saved reel thumbnail: {filename}")
                except Exception as e:
                    self.log(f"Error saving reel thumbnail: {e}")

            # Then download all regular posts
            self.log("=== DOWNLOADING REGULAR POSTS ===")
            for index, post_url in enumerate(post_links):
                driver.get(post_url)
                delay(2, 3)

                self.log(f"[Post {index+1}/{len(post_links)}] {post_url}")
                
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
                        
                        # Log all found video URLs and their sizes
                        self.log(f"Found {len(sorted_candidates)} video candidates:")
                        for url, size in sorted_candidates[:3]:
                            self.log(f"Size: {size/1024/1024:.2f}MB - URL: {url[:50]}...")
                        
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
                media_urls = self.get_all_images_from_carousel(driver)
                self.log(f"Found {len(media_urls)} images in this post")

                # Download images
                for img_index, media_url in enumerate(media_urls):
                    try:
                        filename = f"post_{index+1}_img_{img_index+1}.jpg"
                        save_path = os.path.join(save_folder, filename)
                        if not os.path.exists(save_path):
                            urllib.request.urlretrieve(media_url, save_path)
                            self.log(f"Saved: {filename}")
                        else:
                            self.log(f"Skipped (exists): {filename}")
                    except Exception as e:
                        self.log(f"Download error: {e}")

            self.log("✅ Download Complete.")

        except Exception as e:
            self.log(f"Error during download: {e}")
            raise e
        finally:
            driver.quit()

if __name__ == "__main__":
    app = InstaDownloader()
    app.mainloop() 
