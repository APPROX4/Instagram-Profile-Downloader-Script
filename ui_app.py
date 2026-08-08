import os
import re
import sys
import time
import threading
import queue
import datetime
from tkinter import END

import customtkinter as ctk
from PIL import Image as PILImage

from config import ConfigManager
from instagram_bot import InstagramBot


# ═══════════════════════════════════════════════════════════════
#  COLOUR PALETTE & DESIGN TOKENS
# ═══════════════════════════════════════════════════════════════

BG_MAIN        = "#0F0F11"       # Window background (behind the card)
BG_CARD        = "#131224"       # Main card / panel background
BG_INPUT       = "#24204D"       # Input boxes & log box
TEXT           = "#F2F2F3"       # Primary text
TEXT_MUTED     = "#8B8B99"       # Placeholder / muted text
ACCENT_START   = "#483F9D"       # Start button background
ACCENT_START_H = "#302967"       # Start button hover
ACCENT_STOP    = "#8C366F"       # Stop button background
ACCENT_STOP_H  = "#5F254B"       # Stop button hover
TOGGLE_TRACK   = "#24204D"       # Toggle switch track
CHECKBOX_FG    = "#3D358B"       # Checkbox fill colour
COPY_BTN_BG    = "#2E2966"       # Copy log button background
COPY_BTN_HVR   = "#302967"       # Copy log button hover
LOG_FG         = "#B8C0D8"       # Log text colour
SUCCESS        = "#00E676"
ERROR          = "#FF5252"
WARNING        = "#FFD740"
EYE_COLOR      = "#9090B0"
CARD_OX = 52
CARD_OY = 4


# ═══════════════════════════════════════════════════════════════
#  APPLICATION
# ═══════════════════════════════════════════════════════════════

class IntajectionApp(ctk.CTk):
    """INTAJECTION — Main application window."""

    WIDTH  = 666
    HEIGHT = 597

    def __init__(self):
        super().__init__()

        # ── Window ─────────────────────────────────────────────
        self.title("INTAJECTION")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(self.WIDTH, self.HEIGHT)
        self.maxsize(self.WIDTH, self.HEIGHT)
        self.configure(fg_color=BG_MAIN)
        self.resizable(False, False)

        # ── State ──────────────────────────────────────────────
        self.config_mgr = ConfigManager()
        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.bot_thread: threading.Thread | None = None
        self.active_bot: InstagramBot | None = None
        self.is_running = False

        # ── Build UI ───────────────────────────────────────────
        self._build_ui()

        # ── Load saved credentials ─────────────────────────────
        self._load_saved_creds()

        # ── Start log-queue poller ─────────────────────────────
        self._poll_log_queue()

        # ── Graceful close ─────────────────────────────────────
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ═══════════════════════════════════════════════════════════
    #  UI BUILDER
    # ═══════════════════════════════════════════════════════════

    def _p(self, wx, wy):
        return (wx + CARD_OX, wy + CARD_OY)

    def _get_logo_path(self):
        """Resolve the logo path, works both in dev and PyInstaller."""
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, "logo", "intajection.png")

    def _build_ui(self):
        # ── Background card ────────────────────────────────────
        # Oversized frame at (-52,-4) so its edges sit outside the
        # window and the rounded corners frame the visible area.
        # ALL widgets are children of this frame so that
        # fg_color="transparent" inherits #131224 — no dark bars.
        self.bg_card = ctk.CTkFrame(
            self, fg_color=BG_CARD, border_width=0,
            corner_radius=23, width=864, height=613,
        )
        self.bg_card.place(x=-52, y=-4)
        c = self.bg_card   # shorthand — every widget goes here

        # ────────────────────────────────────────────────────────
        #  LOGO + TITLE
        # ────────────────────────────────────────────────────────
        logo_path = self._get_logo_path()
        if os.path.exists(logo_path):
            logo_img = PILImage.open(logo_path)
            # Scale to fit header height (~40px tall)
            aspect = logo_img.width / logo_img.height
            logo_h = 40
            logo_w = int(aspect * logo_h)
            self.logo_ctk = ctk.CTkImage(
                light_image=logo_img, dark_image=logo_img,
                size=(logo_w, logo_h),
            )
            x, y = self._p(62, 6)
            self.logo_label = ctk.CTkLabel(
                c, image=self.logo_ctk, text="",
                fg_color="transparent",
            )
            self.logo_label.place(x=x, y=y)
            # Title text to the right of the logo
            title_x = x + logo_w + 12
        else:
            title_x, _ = self._p(160, 6)

        x, y = title_x, self._p(0, 10)[1]
        self.title_label = ctk.CTkLabel(
            c, text="INTAJECTION",
            text_color=TEXT, fg_color="transparent",
            font=("Segoe UI", 22, "bold"),
            width=260, height=32,
        )
        self.title_label.place(x=x, y=y)

        # ────────────────────────────────────────────────────────
        #  USERNAME / EMAIL
        # ────────────────────────────────────────────────────────
        x, y = self._p(31, 113)
        ctk.CTkLabel(
            c, text="USERNAME / EMAIL",
            text_color=TEXT, fg_color="transparent",
            font=("Verdana", 14), anchor="w",
            width=212, height=32, justify="left",
        ).place(x=x, y=y)

        x, y = self._p(31, 148)
        self.username_entry = ctk.CTkEntry(
            c, fg_color=BG_INPUT, border_color=BG_INPUT,
            text_color="#FFFFFF", corner_radius=7,
            font=("Arial", 14), width=296, height=36,
            border_width=1, placeholder_text_color=TEXT_MUTED,
        )
        self.username_entry.place(x=x, y=y)
        self.username_entry.bind("<KeyRelease>", lambda e: self._validate())

        # ────────────────────────────────────────────────────────
        #  PASSWORD
        # ────────────────────────────────────────────────────────
        x, y = self._p(31, 197)
        ctk.CTkLabel(
            c, text="PASSWORD",
            text_color=TEXT, fg_color="transparent",
            font=("Verdana", 14), anchor="w",
            width=212, height=32, justify="left",
        ).place(x=x, y=y)

        x, y = self._p(31, 232)
        self.password_entry = ctk.CTkEntry(
            c, show="●",
            fg_color=BG_INPUT, border_color=BG_INPUT,
            text_color="#FFFFFF", corner_radius=7,
            font=("Arial", 14), width=296, height=36,
            border_width=1, placeholder_text_color=TEXT_MUTED,
        )
        self.password_entry.place(x=x, y=y)
        self.password_entry.bind("<KeyRelease>", lambda e: self._validate())

        # Eye toggle (Seamless inside password entry field)
        x, y = self._p(294, 237)
        self.show_pass_var = ctk.BooleanVar(value=False)
        self.eye_btn = ctk.CTkButton(
            c, text="👁", width=28, height=26,
            font=("Segoe UI Symbol", 14),
            fg_color="transparent",
            hover_color="#2E2866",
            text_color="#8B8B99",
            command=self._toggle_password_visibility,
            corner_radius=5,
        )
        self.eye_btn.place(x=x, y=y)

        # ────────────────────────────────────────────────────────
        #  REMEMBER CHECKBOX
        # ────────────────────────────────────────────────────────
        x, y = self._p(31, 268)
        self.remember_var = ctk.BooleanVar(value=False)
        self.remember_cb = ctk.CTkCheckBox(
            c, text="REMEMBER",
            variable=self.remember_var,
            fg_color=CHECKBOX_FG,
            hover_color="#4A4490",
            text_color=TEXT,
            font=("Arial", 14),
            width=140, height=28,
            corner_radius=4,
            checkbox_height=18, checkbox_width=18,
            checkmark_color="#FFFFFF",
        )
        self.remember_cb.place(x=x, y=y)

        # ────────────────────────────────────────────────────────
        #  TARGET USERNAME / URL
        # ────────────────────────────────────────────────────────
        x, y = self._p(31, 307)
        ctk.CTkLabel(
            c, text="TARGET USERNAME / URL",
            text_color=TEXT, fg_color="transparent",
            font=("Verdana", 14), anchor="w",
            width=212, height=32, justify="left",
        ).place(x=x, y=y)

        x, y = self._p(31, 342)
        self.target_entry = ctk.CTkEntry(
            c, fg_color=BG_INPUT, border_color=BG_INPUT,
            text_color="#FFFFFF", corner_radius=7,
            font=("Arial", 14), width=296, height=36,
            border_width=1, placeholder_text_color=TEXT_MUTED,
        )
        self.target_entry.place(x=x, y=y)
        self.target_entry.bind("<KeyRelease>", lambda e: self._validate())

        # ────────────────────────────────────────────────────────
        #  IMAGE FIRST / REELS FIRST TOGGLE
        # ────────────────────────────────────────────────────────
        x, y = self._p(31, 413)
        ctk.CTkLabel(
            c, text="IMAGE FIRST",
            text_color=TEXT, fg_color="transparent",
            font=("Verdana", 14), anchor="w",
            width=105, height=32, justify="left",
        ).place(x=x, y=y)

        self.order_var = ctk.StringVar(
            value=self.config_mgr.get_download_order()
        )
        x, y = self._p(137, 417)
        self.order_switch = ctk.CTkSwitch(
            c, text="",
            progress_color=BG_INPUT,
            button_color="#FFFFFF",
            button_hover_color="#E0E0E0",
            fg_color=BG_INPUT,
            text_color=TEXT,
            font=("Arial", 14),
            command=self._on_toggle_order,
            width=42, height=28,
        )
        self.order_switch.place(x=x, y=y)

        if self.order_var.get() == "reels_first":
            self.order_switch.select()

        x, y = self._p(177, 413)
        ctk.CTkLabel(
            c, text="REELS FIRST",
            text_color=TEXT, fg_color="transparent",
            font=("Verdana", 14), anchor="w",
            width=105, height=32, justify="left",
        ).place(x=x, y=y)

        # ────────────────────────────────────────────────────────
        #  START DOWNLOAD  &  STOP BUTTONS
        # ────────────────────────────────────────────────────────
        x, y = self._p(31, 466)
        self.start_btn = ctk.CTkButton(
            c, text="START DOWNLOAD",
            fg_color=ACCENT_START, hover_color=ACCENT_START_H,
            text_color="#FFFFFF", corner_radius=8,
            font=("Arial", 14),
            command=self._on_start, state="disabled",
            width=215, height=36,
        )
        self.start_btn.place(x=x, y=y)

        x, y = self._p(254, 466)
        self.stop_btn = ctk.CTkButton(
            c, text="STOP",
            fg_color=ACCENT_STOP, hover_color=ACCENT_STOP_H,
            text_color="#FFFFFF", corner_radius=8,
            font=("Arial", 14),
            command=self._on_stop, state="disabled",
            width=73, height=36,
        )
        self.stop_btn.place(x=x, y=y)

        # ────────────────────────────────────────────────────────
        #  BIG LOG BOX
        # ────────────────────────────────────────────────────────
        x, y = self._p(339, 82)
        self.log_frame = ctk.CTkFrame(
            c, fg_color=BG_INPUT, border_color=BG_INPUT,
            border_width=0, corner_radius=15,
            width=294, height=443,
        )
        self.log_frame.place(x=x, y=y)
        self.log_frame.pack_propagate(False)

        self.log_box = ctk.CTkTextbox(
            self.log_frame, fg_color=BG_INPUT, text_color=LOG_FG,
            font=("Consolas", 11),
            corner_radius=15, border_width=0,
            wrap="word", state="disabled",
        )
        self.log_box.pack(fill="both", expand=True, padx=2, pady=2)

        # ────────────────────────────────────────────────────────
        #  FOOTER — INTAJECTION v2.0
        # ────────────────────────────────────────────────────────
        x, y = self._p(-1, 561)
        self.status_label = ctk.CTkLabel(
            c, text="INTAJECTION v2.0",
            text_color=TEXT, fg_color="transparent",
            font=("Verdana", 12), anchor="center",
            width=180, height=32, justify="center",
        )
        self.status_label.place(x=x, y=y)

        # ────────────────────────────────────────────────────────
        #  COPY LOG BUTTON
        # ────────────────────────────────────────────────────────
        x, y = self._p(541, 535)
        self.copy_btn = ctk.CTkButton(
            c, text="COPY LOG",
            fg_color=COPY_BTN_BG, hover_color=COPY_BTN_HVR,
            text_color="#FFFFFF", corner_radius=4,
            font=("Arial", 10),
            command=self._copy_logs,
            width=90, height=21,
        )
        self.copy_btn.place(x=x, y=y)

    # ═══════════════════════════════════════════════════════════
    #  ACTIONS & LOGIC
    # ═══════════════════════════════════════════════════════════

    def _validate(self):
        """Enable Start only when all required fields are filled."""
        u = self.username_entry.get().strip()
        p = self.password_entry.get().strip()
        t = self.target_entry.get().strip()
        can_start = bool(u and p and t) and not self.is_running
        self.start_btn.configure(
            state="normal" if can_start else "disabled"
        )

    def _toggle_password_visibility(self):
        is_shown = not self.show_pass_var.get()
        self.show_pass_var.set(is_shown)
        show = "" if is_shown else "●"
        self.password_entry.configure(show=show)
        
        # Clean seamless Eye icon color toggle
        if is_shown:
            self.eye_btn.configure(
                text="👁",
                fg_color="transparent",
                hover_color="#2E2866",
                text_color="#FFFFFF"
            )
        else:
            self.eye_btn.configure(
                text="👁",
                fg_color="transparent",
                hover_color="#2E2866",
                text_color="#8B8B99"
            )

    def _on_toggle_order(self):
        """Update order_var based on switch state."""
        if self.order_switch.get():
            self.order_var.set("reels_first")
        else:
            self.order_var.set("images_first")

    def _load_saved_creds(self):
        u, p = self.config_mgr.load_credentials()
        if u and p:
            self.username_entry.insert(0, u)
            self.password_entry.insert(0, p)
            self.remember_var.set(True)
            self._init_log_state()
            self._append_log("🔑 Saved credentials loaded", "success")
        self._validate()

    # ── Start / Stop ───────────────────────────────────────────

    def _on_start(self):
        if self.is_running:
            return

        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        target   = self.target_entry.get().strip()

        if not (username and password and target):
            self._append_log("⚠️  Fill in all fields before starting.")
            return

        # Save or clear credentials
        if self.remember_var.get():
            self.config_mgr.save_credentials(username, password)
        else:
            self.config_mgr.clear_credentials()

        # Save download order
        self.config_mgr.set_download_order(self.order_var.get())

        # UI state
        self.is_running = True
        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal", fg_color=ERROR,
                                hover_color="#FF7777",
                                text_color="#FFFFFF")
        self.status_label.configure(text="INTAJECTION v2.0", text_color=TEXT)
        self._append_log("🚀 Starting download process…")

        # Launch bot in background thread
        self.bot_thread = threading.Thread(
            target=self._bot_worker,
            args=(username, password, target, self.order_var.get()),
            daemon=True,
        )
        self.bot_thread.start()

    def _on_stop(self):
        if not self.is_running:
            return

        self._init_log_state()
        self._append_log("⛔ FORCE STOP — killing browser instantly…", "error")
        self.stop_event.set()
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="INTAJECTION v2.0", text_color=TEXT)

        # Force-kill the browser from the main thread — instant death
        def _force_kill():
            bot = self.active_bot
            if bot and bot.driver:
                try:
                    bot.driver.quit()
                except Exception:
                    pass
                bot.driver = None
            # Reset UI immediately
            self.after(200, self._on_bot_done)

        # Run in a short-lived thread so UI doesn't freeze
        threading.Thread(target=_force_kill, daemon=True).start()

    def _bot_worker(self, username, password, target, order):
        """Runs in a daemon thread – drives the InstagramBot."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        bot = InstagramBot(
            log_callback=self._thread_safe_log,
            stop_flag=self.stop_event,
        )
        self.active_bot = bot
        try:
            bot.run(
                username=username,
                password=password,
                target=target,
                download_order=order,
                base_dir=base_dir,
            )
        except Exception as exc:
            if not self.stop_event.is_set():
                self._thread_safe_log(f"❌ Unhandled: {exc}")
        finally:
            self.active_bot = None
            self.log_queue.put(("__DONE__", ""))

    def _thread_safe_log(self, message: str):
        """Push a log message from the worker thread to the queue."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(("LOG", f"[{ts}]  {message}"))

    # ── Log queue consumer ─────────────────────────────────────

    def _poll_log_queue(self):
        """Process queued log messages on the main thread (60 fps)."""
        try:
            while True:
                kind, msg = self.log_queue.get_nowait()
                if kind == "__DONE__":
                    self._on_bot_done()
                elif kind == "LOG":
                    self._smart_log(msg)
        except queue.Empty:
            pass
        self.after(16, self._poll_log_queue)   # ~60 fps

    def _on_bot_done(self):
        """Called on the main thread when the bot finishes."""
        self.is_running = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled", fg_color=ACCENT_STOP,
                                text_color="#FFFFFF")
        self.status_label.configure(text="INTAJECTION v2.0", text_color=TEXT)
        self._smart_log("✅ Process complete.\n")
        self._validate()

    # ═══════════════════════════════════════════════════════════
    #  SMART LOG SYSTEM — spam-proof, colour-coded, modern
    # ═══════════════════════════════════════════════════════════

    # Noisy patterns to suppress entirely
    _SUPPRESS = [
        re.compile(r"Typing (username|password)", re.I),
        re.compile(r"Cookie dialog", re.I),
        re.compile(r"Dismissed:", re.I),
        re.compile(r"Format conversion note", re.I),
        re.compile(r"Converted WebP", re.I),
        re.compile(r"Clicking Log In", re.I),
        re.compile(r"Waiting for login form", re.I),
        re.compile(r"window\.scrollBy", re.I),
    ]

    # Patterns to collapse (show only latest of each group)
    _COLLAPSE = [
        re.compile(r"stall \d+/\d+", re.I),         # stall counters
        re.compile(r"Attempt \d+/\d+ failed", re.I), # retry spam
        re.compile(r"Retrying in \d+s", re.I),       # retry wait
    ]

    # Dedup cooldown in seconds — same message won't repeat within window
    _DEDUP_WINDOW = 3.0

    # Max lines in the log box before trimming old entries
    _MAX_LOG_LINES = 500

    def _init_log_state(self):
        """Initialise smart-log tracking variables (called once)."""
        if not hasattr(self, "_log_last_msg"):
            self._log_last_msg = ""
            self._log_last_time = 0.0
            self._log_repeat_count = 0
            self._log_collapse_cache: dict = {}
            # Configure colour tags on the underlying tk Text widget
            tw = self.log_box._textbox
            tw.tag_configure("success",  foreground="#56D97E")
            tw.tag_configure("error",    foreground="#FF6B6B")
            tw.tag_configure("warning",  foreground="#FFD740")
            tw.tag_configure("info",     foreground="#64B5F6")
            tw.tag_configure("progress", foreground="#CE93D8")
            tw.tag_configure("muted",    foreground="#6E6E8A")
            tw.tag_configure("normal",   foreground=LOG_FG)
            tw.tag_configure("header",   foreground="#B39DDB")

    def _strip_emojis(self, text: str) -> str:
        """Strip all emojis and symbol icons for a clean text-only log."""
        clean = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2b00-\u2bff\u2000-\u206F]', '', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _detect_level(self, text: str) -> str:
        """Detect log level from message content."""
        lower = text.lower()
        if any(w in lower for w in ("saved", "successful", "complete", "ready")):
            return "success"
        if any(w in lower for w in ("failed", "error", "critical")):
            return "error"
        if any(w in lower for w in ("skipping", "warning", "attempt")):
            return "warning"
        if any(w in lower for w in ("collection done", "order:", "download complete")):
            return "header"
        if any(w in lower for w in ("processing", "opening post", "opening reel")) or ("+" in text and "posts" in lower):
            return "progress"
        if any(w in lower for w in ("configuring", "downloading", "opening instagram", "navigating", "scrolling", "starting")):
            return "info"
        if any(w in lower for w in ("closing", "dismissed", "typing", "wait")):
            return "muted"
        return "normal"

    def _smart_log(self, text: str):
        """Filter, deduplicate, colour-code and display a clean text log message."""
        self._init_log_state()

        # Handle multiline blocks cleanly (e.g. summary reports)
        if "\n" in text:
            for line in text.splitlines():
                if line.strip():
                    self._smart_log(line)
            return

        # ── 1. Suppress noisy patterns ─────────────────────────
        for pat in self._SUPPRESS:
            if pat.search(text):
                return

        # ── 2. Strip the timestamp to get raw message for dedup ─
        raw = re.sub(r"^\[\d{2}:\d{2}:\d{2}]\s*", "", text).strip()
        now = time.time()

        # ── 3. Exact-dedup within cooldown window ──────────────
        if raw == self._log_last_msg and (now - self._log_last_time) < self._DEDUP_WINDOW:
            self._log_repeat_count += 1
            return
        self._log_repeat_count = 0
        self._log_last_msg = raw
        self._log_last_time = now

        # ── 4. Detect level & display clean text ───────────────
        level = self._detect_level(text)
        clean_text = self._strip_emojis(text)
        if clean_text:
            self._append_log(clean_text, level)

        # ── 5. Trim buffer if too long ─────────────────────────
        self._trim_log()

    # ── Low-level log helpers ──────────────────────────────────

    def _append_log(self, text: str, tag: str = "normal"):
        self.log_box.configure(state="normal")
        tw = self.log_box._textbox
        tw.insert(END, text + "\n", tag)
        self.log_box.see(END)
        self.log_box.configure(state="disabled")

    def _trim_log(self):
        """Remove oldest lines when buffer exceeds max."""
        self.log_box.configure(state="normal")
        tw = self.log_box._textbox
        line_count = int(tw.index("end-1c").split(".")[0])
        if line_count > self._MAX_LOG_LINES:
            excess = line_count - self._MAX_LOG_LINES
            tw.delete("1.0", f"{excess + 1}.0")
        self.log_box.configure(state="disabled")

    def _copy_logs(self):
        self.log_box.configure(state="normal")
        content = self.log_box._textbox.get("1.0", END).strip()
        self.log_box.configure(state="disabled")
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self._smart_log("Logs copied to clipboard!")

    def _clear_logs(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", END)
        self.log_box.configure(state="disabled")

    # ── Close ──────────────────────────────────────────────────

    def _on_close(self):
        if self.is_running:
            self.stop_event.set()
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  STANDALONE LAUNCH
# ═══════════════════════════════════════════════════════════════

def launch():
    """Launch the INTAJECTION desktop application."""
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = IntajectionApp()
    app.mainloop()


if __name__ == "__main__":
    launch()
