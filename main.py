import os
import time
import json
import urllib.request
import requests
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from tkinter import *
from tkinter import ttk, messagebox
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
CREDENTIALS_FILE = "credentials.json"  # File to save credentials

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

# === GUI ===
class InstaDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Instagram Downloader")
        self.root.geometry("500x400")
        self.root.resizable(False, False)

        self.username = StringVar()
        self.password = StringVar()
        self.target = StringVar()
        self.use_login = BooleanVar()
        self.remember_me = BooleanVar()

        # Load saved credentials if available
        credentials = load_credentials()
        if credentials:
            self.username.set(credentials['username'])
            self.password.set(credentials['password'])
            self.remember_me.set(True)

        # Widgets
        Label(root, text="Target Username / Profile URL").pack(pady=5)
        Entry(root, textvariable=self.target, width=50).pack()

        Checkbutton(root, text="Use Login (for private profiles)", variable=self.use_login).pack()

        Label(root, text="Your Instagram Username").pack()
        Entry(root, textvariable=self.username, width=30).pack()

        Label(root, text="Your Instagram Password").pack()
        Entry(root, textvariable=self.password, width=30, show="*").pack()

        Checkbutton(root, text="Remember Me", variable=self.remember_me).pack()

        Button(root, text="Start Download", command=self.start_download).pack(pady=10)

        self.log_box = Text(root, height=10, width=60)
        self.log_box.pack(pady=5)

        self.progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=10)

    def log(self, msg):
        self.log_box.insert(END, f"{msg}\n")
        self.log_box.see(END)
        self.root.update()

    def start_download(self):
        try:
            self.download_profile()
        except Exception as e:
            self.log(f"Error: {e}")
            messagebox.showerror("Error", str(e))

    def collect_all_posts(self, driver, profile_url):
        """Improved method to collect all posts including reels"""
        self.log("Collecting all post URLs...")
        post_links = set()
        reel_links = set()
        scroll_attempts = 0
        max_scroll_attempts = 30  # Increased from 20 to 30
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
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)
        driver.execute_cdp_cmd("Network.enable", {})

        try:
            driver.get("https://www.instagram.com/")
            delay()

            # Login if required
            if self.use_login.get():
                self.log("Logging in...")
                delay()
                driver.find_element(By.NAME, "username").send_keys(self.username.get())
                driver.find_element(By.NAME, "password").send_keys(self.password.get())
                driver.find_element(By.NAME, "password").send_keys(Keys.ENTER)
                delay(5, 6)
                self.log("Login successful.")

                # Handle post-login popups
                try:
                    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))).click()
                except: pass
                try:
                    wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))).click()
                except: pass

                if self.remember_me.get():
                    save_credentials(self.username.get(), self.password.get())
                else:
                    if os.path.exists(CREDENTIALS_FILE):
                        os.remove(CREDENTIALS_FILE)

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
            self.progress["maximum"] = total_links
            
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

                self.progress["value"] = index + 1
                self.root.update()
            
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

                self.progress["value"] = len(reel_links) + index + 1
                self.root.update()

            self.log("✅ Download Complete.")

        except Exception as e:
            self.log(f"Error during download: {e}")
            raise e
        finally:
            driver.quit()

if __name__ == "__main__":
    root = Tk()
    app = InstaDownloader(root)
    root.mainloop() 