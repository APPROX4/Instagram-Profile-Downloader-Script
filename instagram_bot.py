"""
INTAJECTION — Instagram Selenium Automation Engine.
Handles browser setup, login, profile scrolling, post collection,
carousel image extraction, reel video capture, and anti-ban measures.
"""

import re
import time
import random
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse

import requests as http_requests  # renamed to avoid selenium conflict

from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FxService
from selenium.webdriver.firefox.options import Options as FxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
)

try:
    from webdriver_manager.firefox import GeckoDriverManager
except ImportError:
    GeckoDriverManager = None

from downloader import DownloadManager


# ═══════════════════════════════════════════════════════════════
#  InstagramBot
# ═══════════════════════════════════════════════════════════════

class InstagramBot:
    """Selenium-based Instagram scraper with anti-ban intelligence."""

    LOGIN_URL = "https://www.instagram.com/accounts/login/"
    BASE_URL = "https://www.instagram.com"

    # ── Anti-ban timing (seconds) ──────────────────────────────
    ACT_MIN, ACT_MAX = 2.0, 5.0          # general action pause
    SCROLL_MIN, SCROLL_MAX = 3.0, 7.0    # between scrolls
    TYPE_MIN, TYPE_MAX = 0.05, 0.15      # per-character typing
    MAX_SCROLL_STALLS = 8                 # scroll-end detection

    # ── Constructor ────────────────────────────────────────────

    def __init__(self, log_callback=None, stop_flag=None):
        self.driver = None
        self.log = log_callback or print
        self.stop_flag = stop_flag        # threading.Event
        self.action_count = 0
        self.post_count = 0
        self.image_posts: List[Dict] = []
        self.reel_posts: List[Dict] = []
        self.download_manager: Optional[DownloadManager] = None

    # ── Flow control helpers ───────────────────────────────────

    def should_stop(self) -> bool:
        return bool(self.stop_flag and self.stop_flag.is_set())

    def _sleep(self, lo: float = None, hi: float = None):
        """Interruptible random-range sleep."""
        lo = lo or self.ACT_MIN
        hi = hi or self.ACT_MAX
        end = time.time() + random.uniform(lo, hi)
        while time.time() < end:
            if self.should_stop():
                return
            time.sleep(min(0.5, end - time.time()))

    def _human_type(self, element, text: str):
        """Character-by-character typing with random delays."""
        for ch in text:
            if self.should_stop():
                return
            element.send_keys(ch)
            time.sleep(random.uniform(self.TYPE_MIN, self.TYPE_MAX))

    def _fast_fill(self, element, text: str):
        """Instant fill (copy-paste mode) for credentials."""
        element.clear()
        element.send_keys(text)

    def _rate_check(self):
        """No-op — all breaks removed per user request."""
        self.action_count += 1

    # ═══════════════════════════════════════════════════════════
    #  BROWSER SETUP
    # ═══════════════════════════════════════════════════════════

    def setup_browser(self) -> bool:
        """Launch Firefox with stealth/anti-detect options."""
        try:
            self.log("🔧 Configuring Firefox WebDriver…")
            opts = FxOptions()

            # ── 720p window ────────────────────────────────────
            opts.add_argument("--width=1280")
            opts.add_argument("--height=720")

            # ── Disable notifications ──────────────────────────
            opts.set_preference("dom.webnotifications.enabled", False)
            opts.set_preference("dom.push.enabled", False)

            # ── Disable password manager / autofill ────────────
            opts.set_preference("signon.rememberSignons", False)
            opts.set_preference("signon.autofillForms", False)
            opts.set_preference("signon.formlessCapture.enabled", False)

            # ── Disable translation ────────────────────────────
            opts.set_preference("browser.translations.automaticallyPopup", False)
            opts.set_preference("browser.translations.enable", False)

            # ── Anti-detection ─────────────────────────────────
            opts.set_preference("dom.webdriver.enabled", False)
            opts.set_preference("useAutomationExtension", False)
            opts.set_preference(
                "general.useragent.override",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0",
            )

            # ── Disable geolocation / media popups ─────────────
            opts.set_preference("geo.enabled", False)
            opts.set_preference("media.autoplay.default", 5)

            # ── Enable performance logging for network capture ─
            opts.set_preference("devtools.netmonitor.enabled", True)

            # ── Resolve geckodriver ────────────────────────────
            try:
                if GeckoDriverManager is not None:
                    self.log("📥 Checking / downloading geckodriver…")
                    svc = FxService(GeckoDriverManager().install())
                else:
                    svc = FxService()
            except Exception as exc:
                self.log(f"⚠️  webdriver-manager issue: {exc}")
                self.log("🔄 Falling back to system geckodriver…")
                svc = FxService()

            self.driver = webdriver.Firefox(service=svc, options=opts)
            self.driver.set_window_size(1280, 720)
            self.driver.set_page_load_timeout(45)
            self.driver.implicitly_wait(0)

            self.log("Firefox WebDriver ready (1280x720)")
            return True

        except WebDriverException as exc:
            self.log(f"❌ WebDriver error: {str(exc)[:250]}")
            self.log("💡 Make sure Firefox is installed on this machine.")
            return False
        except Exception as exc:
            self.log(f"❌ Browser setup failed: {str(exc)[:250]}")
            return False

    # ═══════════════════════════════════════════════════════════
    #  LOGIN
    # ═══════════════════════════════════════════════════════════

    def login(self, username: str, password: str) -> Tuple[bool, str]:
        """Log in to Instagram and handle popups / error states."""
        try:
            self.log("🌐 Opening Instagram login page…")
            self.driver.get(self.LOGIN_URL)
            self._sleep(3, 6)

            # ── Cookie consent ─────────────────────────────────
            self._accept_cookies()

            # ── Wait for form ──────────────────────────────────
            self.log("⏳ Waiting for login form…")
            user_el = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'input[name="email"]')
                )
            )
            pass_el = self.driver.find_element(
                By.CSS_SELECTOR, 'input[name="pass"]'
            )

            # ── Fast Enter credentials (copy/paste style) ─────────────
            user_el.clear()
            self._fast_fill(user_el, username)

            pass_el.clear()
            self._fast_fill(pass_el, password)
            self._sleep(0.2, 0.4)

            # ── Click Log In ───────────────────────────────────
            self.log("🔐 Clicking Log In…")
            login_btn = self.driver.find_element(
                By.CSS_SELECTOR,
                'div[role="button"][aria-label="Log In"], '
                'button[type="submit"]',
            )
            login_btn.click()
            self._sleep(2, 4)

            # ── Error check ────────────────────────────────────
            err = self._check_login_errors()
            if err:
                return False, err

            # ── Dismiss popups (onetap / save info / notifications) ─
            self._handle_post_login_popups()

            # ── Verify ─────────────────────────────────────────
            if self._verify_login():
                self.log("✅ Logged in successfully!")
                return True, "Login successful"
            return False, "Login verification failed — check credentials."

        except TimeoutException:
            return False, "Login page timed out. Check your connection."
        except Exception as exc:
            return False, f"Login error: {str(exc)[:250]}"

    # ── login sub-routines ─────────────────────────────────────

    def _accept_cookies(self):
        try:
            btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[contains(text(),'Allow') or "
                    "contains(text(),'Accept') or "
                    "contains(text(),'Only allow essential')]",
                ))
            )
            btn.click()
            self._sleep(1, 2)
            self.log("🍪 Cookie dialog dismissed")
        except TimeoutException:
            pass

    def _check_login_errors(self) -> Optional[str]:
        # Temporarily drop implicit wait to avoid 5s × N xpath waits
        self.driver.implicitly_wait(0)
        try:
            xpaths = [
                '//p[@id="slfErrorAlert"]',
                '//*[contains(text(),"Sorry, your password was incorrect")]',
                '//*[contains(text(),"The username you entered")]',
                '//*[contains(text(),"Please wait a few minutes")]',
                '//*[contains(text(),"suspicious")]',
                '//*[contains(text(),"challenge")]',
                '//*[contains(text(),"unusual login attempt")]',
                '//*[contains(text(),"temporarily locked")]',
                '//*[contains(text(),"incorrect")]',
            ]
            for xp in xpaths:
                try:
                    elems = self.driver.find_elements(By.XPATH, xp)
                    for el in elems:
                        if el.is_displayed():
                            txt = el.text.strip()
                            if txt:
                                self.log(f"❌ Instagram says: {txt}")
                                return txt
                except Exception:
                    continue

            url = self.driver.current_url
            if "challenge" in url:
                return ("Security challenge detected. "
                        "Verify your account in a normal browser first.")
            if "two_factor" in url:
                return "Two-factor authentication required."
            return None
        finally:
            self.driver.implicitly_wait(5)

    def _handle_post_login_popups(self):
        """Bypass 'Save info', 'onetap', notification popups immediately."""
        self._sleep(1, 2)
        xpaths = [
            "//*[(self::button or @role='button') and (contains(translate(., 'NOTNOW', 'notnow'), 'not now') or contains(., 'Not Now') or contains(., 'Not now'))]",
            "//button[contains(text(), 'Not now') or contains(text(), 'Not Now') or contains(text(), 'Save Info') or contains(text(), 'Save')]",
            "//div[@role='button'][contains(text(), 'Not now') or contains(text(), 'Not Now') or contains(text(), 'Save')]",
            "//div[text()='Not now' or text()='Not Now' or text()='Save']",
        ]
        for xp in xpaths:
            try:
                elems = self.driver.find_elements(By.XPATH, xp)
                for el in elems:
                    if el.is_displayed():
                        self.driver.execute_script("arguments[0].click();", el)
                        self.log("🔕 Bypassed save login / onetap popup")
                        self._sleep(0.5, 1)
                        return
            except Exception:
                continue

        if "onetap" in self.driver.current_url.lower():
            self.log("🔕 Bypassing onetap screen")

    def _dismiss_popup(self, label: str, buttons: list):
        for txt in buttons:
            try:
                btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((
                        By.XPATH, f'//button[contains(text(),"{txt}")]'
                    ))
                )
                btn.click()
                self.log(f"🔕 Dismissed: {label}")
                return
            except TimeoutException:
                continue

    def _verify_login(self) -> bool:
        try:
            WebDriverWait(self.driver, 12).until(
                lambda d: "/accounts/login" not in d.current_url
            )
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((
                        By.CSS_SELECTOR,
                        'svg[aria-label="Home"], a[href="/"], nav',
                    ))
                )
                return True
            except TimeoutException:
                return "/accounts/login" not in self.driver.current_url
        except TimeoutException:
            return False

    # ═══════════════════════════════════════════════════════════
    #  PROFILE NAVIGATION
    # ═══════════════════════════════════════════════════════════

    def navigate_to_profile(self, target: str) -> Tuple[bool, str]:
        """Go to the target user's profile page."""
        if target.startswith("http"):
            username = urlparse(target).path.strip("/").split("/")[0]
        else:
            username = target.lstrip("@").strip("/").strip()

        url = f"{self.BASE_URL}/{username}/"
        try:
            self.log(f"🔍 Navigating to @{username}…")
            self.driver.get(url)
            self._sleep(3, 5)

            src = self.driver.page_source.lower()
            if "sorry, this page isn't available" in src:
                return False, f"@{username} not found (404)"
            if "this account is private" in src:
                self.log("🔒 Private account — only visible if you follow them.")

            self.log(f"✅ Profile loaded: @{username}")
            return True, username

        except TimeoutException:
            return False, "Profile page timed out."
        except Exception as exc:
            return False, f"Navigation error: {str(exc)[:200]}"

    # ═══════════════════════════════════════════════════════════
    #  SCROLL & COLLECT POSTS
    # ═══════════════════════════════════════════════════════════

    def collect_all_posts(self) -> int:
        """Scroll through the profile grid and collect every post link."""
        self.log("Scrolling profile to collect all posts...")
        posts: Set[str] = set()
        last_new_time = time.time()
        scroll_n = 0

        while True:
            if self.should_stop():
                self.log("Stop requested during collection")
                break

            # grab visible links
            found = self._visible_post_links()
            before = len(posts)
            posts.update(found)
            delta = len(posts) - before

            if delta > 0:
                last_new_time = time.time()
                self.log(f"+{delta} posts (total {len(posts)})")

            # 15s timeout check if no new posts have been found
            if time.time() - last_new_time >= 15.0:
                self.log("No new content found in 15 seconds. Proceeding to download...")
                break

            # scroll
            scroll_n += 1
            self.driver.execute_script("window.scrollBy(0, window.innerHeight * 0.85);")
            self._sleep(0.6, 1.2)

            # micro-jitter every 6 scrolls
            if scroll_n % 6 == 0:
                self.driver.execute_script(f"window.scrollBy(0,{random.randint(-80, -30)});")
                self._sleep(0.3, 0.6)
                self.driver.execute_script(f"window.scrollBy(0,{random.randint(40, 90)} );")
                self._sleep(0.3, 0.5)

        # categorise
        for href in posts:
            pid = self._post_id(href)
            info = {"url": href, "id": pid}
            if "/reel/" in href or "/reels/" in href:
                self.reel_posts.append(info)
            else:
                self.image_posts.append(info)

        self.log(
            f"Collection done -> "
            f"{len(self.image_posts)} image posts, "
            f"{len(self.reel_posts)} reels"
        )
        return len(posts)

    def _visible_post_links(self) -> Set[str]:
        links: Set[str] = set()
        try:
            elems = self.driver.find_elements(
                By.CSS_SELECTOR, 'a[href*="/p/"], a[href*="/reel/"]'
            )
            for a in elems:
                try:
                    href = a.get_attribute("href")
                    if href and ("/p/" in href or "/reel/" in href):
                        links.add(href)
                except StaleElementReferenceException:
                    continue
        except Exception as exc:
            self.log(f"⚠️  Link scan error: {str(exc)[:100]}")
        return links

    # ═══════════════════════════════════════════════════════════
    #  IMAGE POST PROCESSING
    # ═══════════════════════════════════════════════════════════

    def process_image_posts(self, dm: DownloadManager):
        total = len(self.image_posts)
        self.log(f"Processing {total} image posts...")

        for i, post in enumerate(self.image_posts):
            if self.should_stop():
                break
            self.post_count += 1
            self._rate_check()

            self.log(f"[{i + 1}/{total}] Opening post {post['id']}...")
            try:
                self.driver.get(post["url"])
                self._sleep(0.4, 0.8)

                n = self._collect_images(post["id"], dm)
                self._check_post_video(post["id"], dm)
                self.log(f"    Saved {n} image(s) from post {post['id']}")

            except Exception as exc:
                self.log(f"    Error: {str(exc)[:150]}")

            self._sleep(0.3, 0.6)

    def _collect_images(self, pid: str, dm: DownloadManager) -> int:
        """Walk through a (possibly carousel) post and download images instantly."""
        collected = 0
        seen: Set[str] = set()

        # Wait briefly for page images to exist, but NEVER fail or skip the post
        try:
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR, 'img[src*="instagram"], img[src*="fbcdn"], article, main'
                ))
            )
        except Exception:
            pass

        for _ in range(30):
            if self.should_stop():
                break

            images = self._main_post_images()
            for src in images:
                if src not in seen and self._valid_img(src):
                    seen.add(src)
                    dm.download_image(src, pid, collected)
                    collected += 1

            if not self._carousel_next():
                break

            self._sleep(0.15, 0.3)

        return collected

    def _main_post_images(self) -> List[str]:
        """Return high-res image URLs from the main post in 1ms via JS (excluding suggestions)."""
        try:
            return self.driver.execute_script("""
                const imgs = [];
                const container = document.querySelector('article') || document.querySelector('main') || document.body;
                
                container.querySelectorAll('img').forEach(img => {
                    let isSuggested = false;
                    let p = img.parentElement;
                    for (let i = 0; i < 12; i++) {
                        if (!p) break;
                        const txt = (p.innerText || '').toLowerCase();
                        if (txt.includes('more posts') || txt.includes('suggested for you') || txt.includes('related accounts')) {
                            isSuggested = true;
                            break;
                        }
                        p = p.parentElement;
                    }
                    
                    if (!isSuggested) {
                        const src = img.getAttribute('src') || '';
                        if (src && (src.includes('instagram') || src.includes('fbcdn') || src.includes('cdninstagram'))) {
                            if (!src.includes('150x150') && !src.includes('s150x150') && !src.includes('s64x64') && !src.includes('44x44')) {
                                imgs.push(src);
                            }
                        }
                    }
                });
                return imgs;
            """) or []
        except Exception:
            return []

    @staticmethod
    def _valid_img(src: str) -> bool:
        if not src:
            return False
        for skip in ("150x150", "s150x150", "s64x64", "s128x128",
                      "44x44", "s44x44"):
            if skip in src:
                return False
        return any(d in src for d in ("instagram", "fbcdn", "cdninstagram"))

    def _carousel_next(self) -> bool:
        """Click carousel 'Next' arrow instantly via JS in 1ms."""
        try:
            return bool(self.driver.execute_script("""
                const sel = 'button[aria-label="Next"], button._afxw, button[aria-label="Go Forward"], div._aaqg button';
                const btn = document.querySelector(sel);
                if (btn && btn.offsetWidth > 0 && btn.offsetHeight > 0) {
                    btn.click();
                    return true;
                }
                return false;
            """))
        except Exception:
            return False

    def _check_post_video(self, pid: str, dm: DownloadManager):
        """If an image-post also contains embedded video, grab it."""
        try:
            for vid in self.driver.find_elements(
                By.CSS_SELECTOR,
                "article video, div[role='presentation'] video",
            ):
                try:
                    src = vid.get_attribute("src")
                    if src and src.startswith("http"):
                        dm.download_reel(src, f"{pid}_vid")
                    elif src and src.startswith("blob:"):
                        self.log(
                            f"    📹 Blob video in {pid} — "
                            f"trying page-data extraction…"
                        )
                        real = self._video_from_page(pid)
                        if real:
                            dm.download_reel(real, f"{pid}_vid")
                except StaleElementReferenceException:
                    continue
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    #  REEL POST PROCESSING
    # ═══════════════════════════════════════════════════════════

    def process_reel_posts(self, dm: DownloadManager):
        total = len(self.reel_posts)
        self.log(f"\n🎬 Processing {total} reel posts…")

        for i, reel in enumerate(self.reel_posts):
            if self.should_stop():
                break
            self.post_count += 1
            self._rate_check()

            self.log(f"\n🎥 [{i + 1}/{total}] Opening reel {reel['id']}…")
            try:
                self.driver.get(reel["url"])
                self._sleep(3, 5)

                url = self._best_reel_url(reel["id"])
                if url:
                    dm.download_reel(url, reel["id"])
                else:
                    self.log(f"    ⚠️  Could not extract video for {reel['id']}")
            except Exception as exc:
                self.log(f"    ❌ Error: {str(exc)[:150]}")

            self._sleep(2, 4)

    def _best_reel_url(self, rid: str) -> Optional[str]:
        """Try several strategies to get the best-quality reel URL."""

        # 1 – direct <video> src
        try:
            vid = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "video"))
            )
            s = vid.get_attribute("src")
            if s and s.startswith("http"):
                self.log(f"    🎯 Direct video src found")
                return s
        except TimeoutException:
            pass

        # 2 – <video><source> elements
        try:
            best, best_q = None, 0
            for src_el in self.driver.find_elements(
                By.CSS_SELECTOR, "video source"
            ):
                s = src_el.get_attribute("src")
                if s and ".mp4" in s:
                    q = self._guess_quality(s)
                    if q > best_q:
                        best_q, best = q, s
            if best:
                self.log("    🎯 Best <source> element selected")
                return best
        except Exception:
            pass

        # 3 – embedded page JSON / og:video
        url = self._video_from_page(rid)
        if url:
            return url

        # 4 – performance resource entries
        url = self._video_from_perf(rid)
        if url:
            return url

        return None

    # ── video extraction helpers ───────────────────────────────

    def _video_from_page(self, pid: str) -> Optional[str]:
        """Scrape video URL from meta tags / inline JSON."""
        try:
            for m in self.driver.find_elements(
                By.CSS_SELECTOR, 'meta[property="og:video"]'
            ):
                c = m.get_attribute("content")
                if c and ".mp4" in c:
                    self.log(f"    🎯 og:video meta for {pid}")
                    return c

            page = self.driver.page_source
            patterns = [
                r'"video_url"\s*:\s*"([^"]+\.mp4[^"]*)"',
                r'"src"\s*:\s*"(https?://[^"]+\.mp4[^"]*)"',
                r'"video_versions"\s*:\s*\[.*?"url"\s*:\s*"([^"]+)"',
            ]
            best, best_sz = None, 0
            for pat in patterns:
                for raw in re.findall(pat, page):
                    u = raw.replace("\\u0026", "&").replace("\\/", "/")
                    if u.startswith("http"):
                        sz = self._head_size(u)
                        if sz > best_sz:
                            best_sz, best = sz, u
            if best:
                self.log(
                    f"    🎯 Page-data video ({best_sz // 1024} KB)"
                )
                return best
        except Exception:
            pass
        return None

    def _video_from_perf(self, pid: str) -> Optional[str]:
        """Check performance.getEntriesByType('resource') for mp4."""
        try:
            entries = self.driver.execute_script("""
                return performance.getEntriesByType('resource')
                    .filter(e => e.name.includes('.mp4') ||
                                 e.name.includes('/video/'))
                    .map(e => ({url: e.name, size: e.transferSize || 0}));
            """)
            if entries:
                entries.sort(key=lambda x: x.get("size", 0), reverse=True)
                self.log(
                    f"    🎯 Network resource ({len(entries)} mp4 candidates)"
                )
                return entries[0]["url"]
        except Exception:
            pass
        return None

    @staticmethod
    def _guess_quality(url: str) -> int:
        for r in (1080, 720, 480, 360):
            if str(r) in url:
                return r
        return 500

    @staticmethod
    def _head_size(url: str) -> int:
        try:
            r = http_requests.head(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                        "Gecko/20100101 Firefox/128.0"
                    ),
                    "Referer": "https://www.instagram.com/",
                },
                timeout=10,
                allow_redirects=True,
            )
            return int(r.headers.get("content-length", 0))
        except Exception:
            return 0

    # ── Misc helpers ───────────────────────────────────────────

    @staticmethod
    def _post_id(url: str) -> str:
        """Extract the actual post/reel code from a URL.

        Handles both formats:
          - https://instagram.com/p/CODE123/
          - https://instagram.com/username/p/CODE123/
          - https://instagram.com/reel/CODE123/
        """
        try:
            parts = urlparse(url).path.strip("/").split("/")
            # Find 'p' or 'reel'/'reels' and take the NEXT segment
            for i, segment in enumerate(parts):
                if segment in ("p", "reel", "reels") and i + 1 < len(parts):
                    code = parts[i + 1]
                    if code:  # non-empty
                        return code
        except Exception:
            pass
        return f"unk_{random.randint(1000, 9999)}"

    # ═══════════════════════════════════════════════════════════
    #  MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════════

    def run(
        self,
        username: str,
        password: str,
        target: str,
        download_order: str = "images_first",
        base_dir: str = ".",
    ) -> bool:
        """Full execution pipeline."""
        try:
            # 1 – browser
            if not self.setup_browser():
                return False
            if self.should_stop():
                return False

            # 2 – login
            ok, msg = self.login(username, password)
            if not ok:
                self.log(f"❌ Login failed: {msg}")
                return False
            if self.should_stop():
                return False
            self._sleep(2, 4)

            # 3 – profile
            ok, result = self.navigate_to_profile(target)
            if not ok:
                self.log(f"❌ {result}")
                return False
            target_user = result
            if self.should_stop():
                return False

            # 4 – download manager
            dm = DownloadManager(base_dir, target_user, self.log)
            self.download_manager = dm
            dm.start_timer()

            # 5 – collect posts
            self.collect_all_posts()
            if self.should_stop():
                self.log(dm.get_summary())
                return False

            # 6 – download media
            if download_order == "images_first":
                self.log("\n📋 Order: Images → Reels")
                self.process_image_posts(dm)
                if not self.should_stop():
                    self.process_reel_posts(dm)
            else:
                self.log("\n📋 Order: Reels → Images")
                self.process_reel_posts(dm)
                if not self.should_stop():
                    self.process_image_posts(dm)

            # 7 – summary
            total_posts = len(self.image_posts) + len(self.reel_posts)
            self.log(dm.get_summary(total_posts))
            return True

        except Exception as exc:
            self.log(f"❌ Critical error: {str(exc)[:300]}")
            return False

        finally:
            self.cleanup()

    def cleanup(self):
        try:
            if self.driver:
                self.log("🧹 Closing browser…")
                self.driver.quit()
                self.driver = None
        except Exception:
            pass
