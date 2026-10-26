"""
User Interface module for QR Secure Notes.
Modern dark navy / charcoal desktop GUI built with standard Python Tkinter and ttk.
Features:
- Sidebar navigation (Dashboard, Create Note, Scan QR, My Notes, Security & Help, Settings)
- Real-time password strength meter and character counter
- QR generation, live preview, and PNG export
- File import and live OpenCV webcam QR scanning
- SQLite note manager with search, filter, export, and unlock dialogs
- Educational security and cryptography guide
- Live database backup tool
"""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from PIL import Image, ImageTk
import cv2

from config import (
    APP_NAME,
    APP_SUBTITLE,
    APP_VERSION,
    THEME,
    DB_PATH,
    EXPORTS_DIR,
    MAX_CONTENT_CHARS,
    MAX_TITLE_CHARS,
    logger,
)
from note_manager import NoteManager, PasswordStrength
import qr_manager
import database
import encryption


class ModernTheme:
    """Applies modern dark styling to standard ttk widgets."""

    @staticmethod
    def apply(root: tk.Tk) -> None:
        style = ttk.Style(root)
        style.theme_use("clam")

        # Configure root window background
        root.configure(bg=THEME["bg_dark"])

        # Base Frame styles
        style.configure("TFrame", background=THEME["bg_dark"])
        style.configure("Sidebar.TFrame", background=THEME["bg_sidebar"])
        style.configure("Card.TFrame", background=THEME["bg_card"], relief="flat")
        style.configure("CardAlt.TFrame", background=THEME["bg_card_alt"], relief="flat")

        # Base Label styles
        style.configure("TLabel", background=THEME["bg_dark"], foreground=THEME["text_primary"], font=(THEME["font_family"], 10))
        style.configure("Sidebar.TLabel", background=THEME["bg_sidebar"], foreground=THEME["text_primary"], font=(THEME["font_family"], 10))
        style.configure("Card.TLabel", background=THEME["bg_card"], foreground=THEME["text_primary"], font=(THEME["font_family"], 10))
        style.configure("CardAlt.TLabel", background=THEME["bg_card_alt"], foreground=THEME["text_primary"], font=(THEME["font_family"], 10))
        style.configure("Header.TLabel", background=THEME["bg_dark"], foreground=THEME["text_primary"], font=(THEME["font_family"], 16, "bold"))
        style.configure("Subheader.TLabel", background=THEME["bg_dark"], foreground=THEME["text_secondary"], font=(THEME["font_family"], 10))
        style.configure("CardHeader.TLabel", background=THEME["bg_card"], foreground=THEME["accent_blue"], font=(THEME["font_family"], 12, "bold"))

        # Base Button styles
        style.configure(
            "Primary.TButton",
            background=THEME["accent_blue"],
            foreground="#ffffff",
            font=(THEME["font_family"], 10, "bold"),
            borderwidth=0,
            focusthickness=0,
            padding=8,
        )
        style.map(
            "Primary.TButton",
            background=[("active", THEME["accent_hover"]), ("disabled", THEME["text_disabled"])],
        )

        style.configure(
            "Secondary.TButton",
            background=THEME["bg_card_alt"],
            foreground=THEME["text_primary"],
            font=(THEME["font_family"], 10),
            borderwidth=1,
            bordercolor=THEME["border"],
            padding=7,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", THEME["border"])],
        )

        style.configure(
            "Danger.TButton",
            background=THEME["danger"],
            foreground="#ffffff",
            font=(THEME["font_family"], 10, "bold"),
            borderwidth=0,
            padding=7,
        )
        style.map("Danger.TButton", background=[("active", "#dc2626")])

        # Navigation buttons
        style.configure(
            "Nav.TButton",
            background=THEME["bg_sidebar"],
            foreground=THEME["text_secondary"],
            font=(THEME["font_family"], 11),
            borderwidth=0,
            anchor="w",
            padding=10,
        )
        style.map(
            "Nav.TButton",
            background=[("active", THEME["bg_card"]), ("selected", THEME["bg_card"])],
            foreground=[("active", THEME["text_primary"]), ("selected", THEME["accent_blue"])],
        )

        # Treeview styling for data tables
        style.configure(
            "Treeview",
            background=THEME["bg_card"],
            foreground=THEME["text_primary"],
            fieldbackground=THEME["bg_card"],
            borderwidth=0,
            font=(THEME["font_family"], 10),
            rowheight=32,
        )
        style.map("Treeview", background=[("selected", THEME["accent_blue"])], foreground=[("selected", "#ffffff")])
        style.configure(
            "Treeview.Heading",
            background=THEME["bg_sidebar"],
            foreground=THEME["text_primary"],
            font=(THEME["font_family"], 10, "bold"),
            borderwidth=0,
            padding=6,
        )

        # Combobox / Entry styling
        style.configure("TCombobox", fieldbackground=THEME["bg_input"], background=THEME["bg_card"], foreground="#ffffff", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", THEME["bg_input"])], foreground=[("readonly", "#ffffff")])


class QRSecureNotesApp:
    """Main Application Controller and Window."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1100x720")
        self.root.minsize(980, 640)

        # Apply dark theme
        ModernTheme.apply(self.root)

        # Note manager backend
        self.note_mgr = NoteManager(DB_PATH)

        # Webcam scanner instance
        self.scanner = qr_manager.WebcamScanner()
        self.webcam_job = None

        # Cache for created/scanned QR preview
        self.current_preview_photo: Optional[ImageTk.PhotoImage] = None
        self.current_created_note_data: Optional[Dict[str, Any]] = None

        # Build application shell
        self._build_layout()
        self._show_view("dashboard")

        # Clean exit hook
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self) -> None:
        """Constructs sidebar, content container, and bottom status bar."""
        # Main vertical container
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # Sidebar (Left)
        self.sidebar = ttk.Frame(self.main_container, style="Sidebar.TFrame", width=220)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Main content area (Right)
        self.content_area = ttk.Frame(self.main_container, style="TFrame")
        self.content_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._build_sidebar()
        self._build_status_bar()

    def _build_sidebar(self) -> None:
        """Sidebar with application brand and view navigation buttons."""
        brand_frame = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        brand_frame.pack(fill=tk.X, padx=16, pady=20)

        title_lbl = ttk.Label(
            brand_frame,
            text="QR SECURE NOTES",
            font=(THEME["font_family"], 13, "bold"),
            foreground=THEME["accent_blue"],
            background=THEME["bg_sidebar"]
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ttk.Label(
            brand_frame,
            text=APP_SUBTITLE,
            font=(THEME["font_family"], 8),
            foreground=THEME["text_secondary"],
            background=THEME["bg_sidebar"]
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Divider
        sep = tk.Frame(self.sidebar, height=1, bg=THEME["border"])
        sep.pack(fill=tk.X, padx=12, pady=(0, 15))

        # Navigation items
        self.nav_buttons = {}
        nav_items = [
            ("dashboard", "Dashboard"),
            ("create", "Create Secure Note"),
            ("scan", "Scan QR Code"),
            ("my_notes", "My Notes"),
            ("security", "Security & Help"),
            ("settings", "Settings"),
        ]

        for key, label in nav_items:
            btn = ttk.Button(
                self.sidebar,
                text=f"  {label}",
                style="Nav.TButton",
                command=lambda k=key: self._show_view(k)
            )
            btn.pack(fill=tk.X, padx=10, pady=3)
            self.nav_buttons[key] = btn

        # Offline & Security Badge at sidebar bottom
        bottom_box = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        bottom_box.pack(side=tk.BOTTOM, fill=tk.X, padx=14, pady=16)

        shield_lbl = ttk.Label(
            bottom_box,
            text="Authenticated AES-256-GCM\nOffline SQLite Protected",
            font=(THEME["font_family"], 8),
            foreground=THEME["text_disabled"],
            background=THEME["bg_sidebar"],
            justify="center"
        )
        shield_lbl.pack(fill=tk.X)

    def _build_status_bar(self) -> None:
        """Bottom status bar with database and cryptographic engine status."""
        self.status_bar = tk.Frame(self.root, height=26, bg=THEME["bg_sidebar"], bd=0)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_db_lbl = tk.Label(
            self.status_bar,
            text=" Database: Connected (Local SQLite)",
            font=(THEME["font_family"], 8),
            fg=THEME["success"],
            bg=THEME["bg_sidebar"]
        )
        self.status_db_lbl.pack(side=tk.LEFT, padx=12)

        self.status_msg_lbl = tk.Label(
            self.status_bar,
            text="Ready",
            font=(THEME["font_family"], 8),
            fg=THEME["text_secondary"],
            bg=THEME["bg_sidebar"]
        )
        self.status_msg_lbl.pack(side=tk.RIGHT, padx=14)

    def set_status(self, message: str, is_error: bool = False) -> None:
        color = THEME["danger"] if is_error else THEME["text_secondary"]
        self.status_msg_lbl.config(text=message, fg=color)

    def _show_view(self, view_key: str) -> None:
        """Switches active view panel in the content area."""
        # Stop webcam if moving away from scanner
        if view_key != "scan":
            self._stop_webcam()

        # Update sidebar highlight
        for k, btn in self.nav_buttons.items():
            if k == view_key:
                btn.configure(style="Primary.TButton")
            else:
                btn.configure(style="Nav.TButton")

        # Clear existing view children
        for child in self.content_area.winfo_children():
            child.destroy()

        # Route to view generator
        if view_key == "dashboard":
            self._render_dashboard()
        elif view_key == "create":
            self._render_create_note()
        elif view_key == "scan":
            self._render_scan_qr()
        elif view_key == "my_notes":
            self._render_my_notes()
        elif view_key == "security":
            self._render_security_help()
        elif view_key == "settings":
            self._render_settings()

    # =========================================================================
    # VIEW 1: DASHBOARD
    # =========================================================================
    def _render_dashboard(self) -> None:
        container = ttk.Frame(self.content_area, style="TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        # Header
        header = ttk.Label(container, text="Security Dashboard", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(container, text="Overview of local encrypted notes and QR sessions.", style="Subheader.TLabel")
        sub.pack(anchor="w", pady=(2, 16))

        # Fetch real statistics
        summary = self.note_mgr.get_dashboard_summary()
        stats = summary["stats"]

        # Statistics Cards Grid
        stats_frame = ttk.Frame(container, style="TFrame")
        stats_frame.pack(fill=tk.X, pady=(0, 20))

        cards_data = [
            ("TOTAL SAVED NOTES", str(stats["total_notes"]), THEME["accent_blue"]),
            ("ACTIVE NOTES", str(stats["active_notes"]), THEME["success"]),
            ("EXPIRED NOTES", str(stats["expired_notes"]), THEME["warning"]),
            ("SESSION QR CODES", str(stats["session_qr_generated"]), THEME["accent_violet"]),
        ]

        for i, (title, val, color) in enumerate(cards_data):
            c_frame = tk.Frame(stats_frame, bg=THEME["bg_card"], bd=0, padx=16, pady=14)
            c_frame.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            stats_frame.columnconfigure(i, weight=1)

            tk.Label(c_frame, text=title, font=(THEME["font_family"], 8, "bold"), fg=THEME["text_secondary"], bg=THEME["bg_card"]).pack(anchor="w")
            tk.Label(c_frame, text=val, font=(THEME["font_family"], 20, "bold"), fg=color, bg=THEME["bg_card"]).pack(anchor="w", pady=(4, 0))

        # Quick Actions Row
        action_frame = tk.Frame(container, bg=THEME["bg_card"], padx=18, pady=16)
        action_frame.pack(fill=tk.X, pady=(0, 20))

        tk.Label(action_frame, text="Quick Actions", font=(THEME["font_family"], 11, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 10))

        btn_box = ttk.Frame(action_frame, style="Card.TFrame")
        btn_box.pack(anchor="w")

        ttk.Button(btn_box, text="+ Create Secure Note", style="Primary.TButton", command=lambda: self._show_view("create")).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_box, text="Import & Decrypt QR", style="Secondary.TButton", command=lambda: self._show_view("scan")).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_box, text="Open My Notes", style="Secondary.TButton", command=lambda: self._show_view("my_notes")).pack(side=tk.LEFT)

        # Recent Notes List / Empty State
        recent_box = tk.Frame(container, bg=THEME["bg_card"], padx=18, pady=16)
        recent_box.pack(fill=tk.BOTH, expand=True)

        tk.Label(recent_box, text="Recently Saved Encrypted Notes", font=(THEME["font_family"], 11, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 10))

        recent_notes = summary["recent_notes"]
        if not recent_notes:
            empty_frame = tk.Frame(recent_box, bg=THEME["bg_card"], pady=30)
            empty_frame.pack(fill=tk.BOTH, expand=True)
            tk.Label(empty_frame, text="No encrypted notes stored in local SQLite database yet.", font=(THEME["font_family"], 11), fg=THEME["text_secondary"], bg=THEME["bg_card"]).pack()
            tk.Label(empty_frame, text="Click '+ Create Secure Note' to create and encrypt your first note.", font=(THEME["font_family"], 9), fg=THEME["text_disabled"], bg=THEME["bg_card"]).pack(pady=4)
        else:
            table_frame = ttk.Frame(recent_box, style="Card.TFrame")
            table_frame.pack(fill=tk.BOTH, expand=True)

            tree = ttk.Treeview(table_frame, columns=("uuid", "cat", "created", "status"), show="headings", height=5)
            tree.heading("uuid", text="Note Identifier (UUID)")
            tree.heading("cat", text="Category")
            tree.heading("created", text="Created (Local)")
            tree.heading("status", text="Status")

            tree.column("uuid", width=220)
            tree.column("cat", width=120)
            tree.column("created", width=180)
            tree.column("status", width=90)

            for n in recent_notes:
                # Format created time
                try:
                    dt = datetime.fromisoformat(n["created_at"]).astimezone()
                    created_disp = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    created_disp = n["created_at"]

                tree.insert("", tk.END, values=(n["note_uuid"], n["category"], created_disp, n["status"].upper()))

            tree.pack(fill=tk.BOTH, expand=True)

    # =========================================================================
    # VIEW 2: CREATE SECURE NOTE
    # =========================================================================
    def _render_create_note(self) -> None:
        container = ttk.Frame(self.content_area, style="TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        header = ttk.Label(container, text="Create Secure Note", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(container, text="Encrypt note title and content using AES-256-GCM and generate an encrypted QR code.", style="Subheader.TLabel")
        sub.pack(anchor="w", pady=(2, 12))

        # Split into Two Columns: Left Form (60%) and Right QR Preview (40%)
        panes_frame = ttk.Frame(container, style="TFrame")
        panes_frame.pack(fill=tk.BOTH, expand=True)

        left_form = tk.Frame(panes_frame, bg=THEME["bg_card"], padx=18, pady=16)
        left_form.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))

        right_preview = tk.Frame(panes_frame, bg=THEME["bg_card"], padx=18, pady=16, width=340)
        right_preview.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_preview.pack_propagate(False)

        # --- Form Elements ---
        # Note Title
        tk.Label(left_form, text="Note Title (Encrypted inside payload)", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w")
        self.entry_title = tk.Entry(left_form, bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat")
        self.entry_title.pack(fill=tk.X, pady=(4, 10), ipady=4)
        self.entry_title.insert(0, "Confidential Note")

        # Category & Expiration Row
        cat_exp_frame = ttk.Frame(left_form, style="Card.TFrame")
        cat_exp_frame.pack(fill=tk.X, pady=(0, 10))

        # Category
        cat_col = ttk.Frame(cat_exp_frame, style="Card.TFrame")
        cat_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        tk.Label(cat_col, text="Category", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w")
        self.combo_category = ttk.Combobox(cat_col, values=["General", "Personal", "Work", "Finance", "Credentials", "Confidential"])
        self.combo_category.current(0)
        self.combo_category.pack(fill=tk.X, pady=(4, 0))

        # Expiration
        exp_col = ttk.Frame(cat_exp_frame, style="Card.TFrame")
        exp_col.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        tk.Label(exp_col, text="Expiration (Optional)", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w")
        self.combo_expiration = ttk.Combobox(exp_col, values=["none", "1_hour", "24_hours", "7_days", "30_days"])
        self.combo_expiration.current(0)
        self.combo_expiration.pack(fill=tk.X, pady=(4, 0))

        # Note Content
        cnt_header_frame = ttk.Frame(left_form, style="Card.TFrame")
        cnt_header_frame.pack(fill=tk.X)
        tk.Label(cnt_header_frame, text="Note Content *", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(side=tk.LEFT)
        self.lbl_char_count = tk.Label(cnt_header_frame, text="0 / 1500 chars", font=(THEME["font_family"], 8), fg=THEME["text_secondary"], bg=THEME["bg_card"])
        self.lbl_char_count.pack(side=tk.RIGHT)

        self.txt_content = tk.Text(left_form, height=7, bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat", wrap="word")
        self.txt_content.pack(fill=tk.BOTH, expand=True, pady=(4, 10))
        self.txt_content.bind("<KeyRelease>", self._update_char_count)

        # Passwords Row
        pwd_frame = ttk.Frame(left_form, style="Card.TFrame")
        pwd_frame.pack(fill=tk.X, pady=(0, 6))

        # Password
        p1_col = ttk.Frame(pwd_frame, style="Card.TFrame")
        p1_col.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        tk.Label(p1_col, text="Encryption Password *", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w")
        self.entry_pass = tk.Entry(p1_col, show="*", bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat")
        self.entry_pass.pack(fill=tk.X, pady=(4, 0), ipady=4)
        self.entry_pass.bind("<KeyRelease>", self._update_password_meter)

        # Confirm Password
        p2_col = ttk.Frame(pwd_frame, style="Card.TFrame")
        p2_col.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        tk.Label(p2_col, text="Confirm Password *", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w")
        self.entry_confirm = tk.Entry(p2_col, show="*", bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat")
        self.entry_confirm.pack(fill=tk.X, pady=(4, 0), ipady=4)

        # Password Strength Bar & Controls
        meter_row = ttk.Frame(left_form, style="Card.TFrame")
        meter_row.pack(fill=tk.X, pady=(0, 10))

        self.strength_canvas = tk.Canvas(meter_row, height=6, bg=THEME["bg_input"], highlightthickness=0)
        self.strength_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=4)

        self.lbl_strength = tk.Label(meter_row, text="Strength: Empty", font=(THEME["font_family"], 8), fg=THEME["text_secondary"], bg=THEME["bg_card"])
        self.lbl_strength.pack(side=tk.LEFT, padx=(8, 12))

        self.btn_toggle_show = ttk.Button(meter_row, text="Show", style="Secondary.TButton", command=self._toggle_password_visibility)
        self.btn_toggle_show.pack(side=tk.RIGHT)

        # Checkboxes
        self.var_save_db = tk.BooleanVar(value=True)
        self.var_auto_export = tk.BooleanVar(value=False)

        cb_frame = ttk.Frame(left_form, style="Card.TFrame")
        cb_frame.pack(fill=tk.X, pady=(0, 12))

        cb1 = tk.Checkbutton(cb_frame, text="Save encrypted note in local SQLite database", variable=self.var_save_db, bg=THEME["bg_card"], fg=THEME["text_primary"], selectcolor=THEME["bg_input"], activebackground=THEME["bg_card"], activeforeground=THEME["text_primary"], font=(THEME["font_family"], 9))
        cb1.pack(anchor="w")

        cb2 = tk.Checkbutton(cb_frame, text="Auto-export generated QR image to exports/ folder", variable=self.var_auto_export, bg=THEME["bg_card"], fg=THEME["text_primary"], selectcolor=THEME["bg_input"], activebackground=THEME["bg_card"], activeforeground=THEME["text_primary"], font=(THEME["font_family"], 9))
        cb2.pack(anchor="w")

        # Buttons
        act_btn_frame = ttk.Frame(left_form, style="Card.TFrame")
        act_btn_frame.pack(fill=tk.X)

        self.btn_generate = ttk.Button(act_btn_frame, text="Generate Secure QR", style="Primary.TButton", command=self._handle_generate_note)
        self.btn_generate.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(act_btn_frame, text="Clear / Reset", style="Secondary.TButton", command=self._reset_create_form).pack(side=tk.LEFT)

        # --- Right Preview Panel ---
        tk.Label(right_preview, text="QR Code Preview", font=(THEME["font_family"], 11, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 8))

        # QR Image Canvas Box
        self.preview_canvas_box = tk.Frame(right_preview, bg=THEME["bg_input"], height=240, bd=1, relief="flat")
        self.preview_canvas_box.pack(fill=tk.X, pady=(0, 10))
        self.preview_canvas_box.pack_propagate(False)

        self.lbl_qr_preview = tk.Label(self.preview_canvas_box, text="Generated QR preview\nwill appear here.", font=(THEME["font_family"], 9), fg=THEME["text_disabled"], bg=THEME["bg_input"])
        self.lbl_qr_preview.pack(fill=tk.BOTH, expand=True)

        # Metadata text
        self.lbl_meta_info = tk.Label(right_preview, text="Payload Metadata:\nAlgorithm: AES-256-GCM\nKDF: Argon2id\nStatus: Waiting for input", font=(THEME["font_family"], 8), fg=THEME["text_secondary"], bg=THEME["bg_card"], justify="left")
        self.lbl_meta_info.pack(anchor="w", pady=(0, 12))

        # Actions on QR
        self.btn_save_qr = ttk.Button(right_preview, text="Save QR Image (PNG)...", style="Secondary.TButton", command=self._export_current_qr, state=tk.DISABLED)
        self.btn_save_qr.pack(fill=tk.X, pady=(0, 6))

        self.btn_copy_json = ttk.Button(right_preview, text="Copy Encrypted JSON", style="Secondary.TButton", command=self._copy_current_payload_json, state=tk.DISABLED)
        self.btn_copy_json.pack(fill=tk.X)

    def _update_char_count(self, event=None) -> None:
        content = self.txt_content.get("1.0", tk.END).strip()
        count = len(content)
        self.lbl_char_count.config(text=f"{count} / {MAX_CONTENT_CHARS} chars")
        if count > MAX_CONTENT_CHARS:
            self.lbl_char_count.config(fg=THEME["danger"])
        else:
            self.lbl_char_count.config(fg=THEME["text_secondary"])

    def _update_password_meter(self, event=None) -> None:
        pwd = self.entry_pass.get()
        info = PasswordStrength.evaluate(pwd)
        score = info["score"]
        color = info["color"]
        label = info["label"]

        self.lbl_strength.config(text=f"Strength: {label}", fg=color)

        self.strength_canvas.delete("all")
        width = self.strength_canvas.winfo_width()
        fill_width = (score / 100.0) * width
        self.strength_canvas.create_rectangle(0, 0, fill_width, 6, fill=color, outline="")

    def _toggle_password_visibility(self) -> None:
        if self.entry_pass.cget("show") == "*":
            self.entry_pass.config(show="")
            self.entry_confirm.config(show="")
            self.btn_toggle_show.config(text="Hide")
        else:
            self.entry_pass.config(show="*")
            self.entry_confirm.config(show="*")
            self.btn_toggle_show.config(text="Show")

    def _reset_create_form(self) -> None:
        self.entry_title.delete(0, tk.END)
        self.entry_title.insert(0, "Confidential Note")
        self.txt_content.delete("1.0", tk.END)
        self.entry_pass.delete(0, tk.END)
        self.entry_confirm.delete(0, tk.END)
        self.combo_category.current(0)
        self.combo_expiration.current(0)
        self._update_char_count()
        self._update_password_meter()
        self.lbl_qr_preview.config(image="", text="Generated QR preview\nwill appear here.")
        self.btn_save_qr.config(state=tk.DISABLED)
        self.btn_copy_json.config(state=tk.DISABLED)
        self.current_preview_photo = None
        self.current_created_note_data = None
        self.set_status("Form reset.")

    def _handle_generate_note(self) -> None:
        title = self.entry_title.get().strip()
        content = self.txt_content.get("1.0", tk.END).strip()
        pwd = self.entry_pass.get()
        confirm = self.entry_confirm.get()
        cat = self.combo_category.get().strip()
        exp = self.combo_expiration.get().strip()

        if not content:
            messagebox.showwarning("Validation Error", "Note content cannot be empty.")
            return

        if not pwd:
            messagebox.showwarning("Validation Error", "Please enter an encryption password.")
            return

        if pwd != confirm:
            messagebox.showerror("Password Mismatch", "Passwords do not match. Please verify your password.")
            return

        try:
            self.btn_generate.config(state=tk.DISABLED)
            self.set_status("Encrypting payload and generating QR code...")
            self.root.update_idletasks()

            result = self.note_mgr.create_secure_note(
                title=title,
                content=content,
                password=pwd,
                confirm_password=confirm,
                category=cat,
                expiration_option=exp,
                save_to_database=self.var_save_db.get(),
                auto_export_qr=self.var_auto_export.get()
            )

            self.current_created_note_data = result

            # Render QR preview image in UI
            pil_img = result["qr_image"]
            preview_resized = pil_img.resize((210, 210), Image.Resampling.LANCZOS)
            self.current_preview_photo = ImageTk.PhotoImage(preview_resized)
            self.lbl_qr_preview.config(image=self.current_preview_photo, text="")

            # Update Metadata text
            uuid_str = result["uuid"]
            kdf_name = result["payload_dict"]["kdf"]["name"]
            payload_len = len(result["serialized_payload"])
            meta_text = (
                f"Note UUID: {uuid_str}\n"
                f"Algorithm: AES-256-GCM\n"
                f"KDF: {kdf_name}\n"
                f"Payload Size: {payload_len} bytes\n"
                f"Database: {'Saved' if result['row_id'] else 'Not saved'}"
            )
            if result.get("auto_exported_path"):
                meta_text += f"\nAuto-exported: {result['auto_exported_path'].name}"

            self.lbl_meta_info.config(text=meta_text)
            self.btn_save_qr.config(state=tk.NORMAL)
            self.btn_copy_json.config(state=tk.NORMAL)

            self.set_status(f"Secure QR created successfully (UUID: {uuid_str}).")
            messagebox.showinfo(
                "Secure QR Created",
                f"Note encrypted and QR code generated successfully!\n\n"
                f"Identifier: {uuid_str}\n"
                f"Saved to Database: {'Yes' if result['row_id'] else 'No'}\n\n"
                f"Remember your password. If forgotten, this note cannot be decrypted!"
            )

        except Exception as e:
            logger.error("Error creating note: %s", str(e))
            self.set_status(f"Error: {str(e)}", is_error=True)
            messagebox.showerror("Error", f"Failed to create secure note:\n{str(e)}")
        finally:
            self.btn_generate.config(state=tk.NORMAL)

    def _export_current_qr(self) -> None:
        if not self.current_created_note_data:
            return
        default_fn = qr_manager.get_default_export_filename(self.current_created_note_data["uuid"])
        path = filedialog.asksaveasfilename(
            initialdir=str(EXPORTS_DIR),
            initialfile=default_fn,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")]
        )
        if path:
            try:
                qr_manager.save_qr_image(self.current_created_note_data["qr_image"], path)
                self.set_status(f"QR code exported to {Path(path).name}")
                messagebox.showinfo("Export Successful", f"QR image saved successfully to:\n{path}")
            except Exception as e:
                messagebox.showerror("Export Failed", str(e))

    def _copy_current_payload_json(self) -> None:
        if not self.current_created_note_data:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_created_note_data["serialized_payload"])
        self.set_status("Encrypted payload JSON copied to clipboard.")
        messagebox.showinfo("Copied", "Encrypted JSON payload copied to clipboard.")

    # =========================================================================
    # VIEW 3: SCAN AND DECRYPT QR CODE
    # =========================================================================
    def _render_scan_qr(self) -> None:
        container = ttk.Frame(self.content_area, style="TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        header = ttk.Label(container, text="Scan & Decrypt QR Code", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(container, text="Import an encrypted QR image or use your webcam to scan and unlock notes.", style="Subheader.TLabel")
        sub.pack(anchor="w", pady=(2, 12))

        # Split: Left side Scanner/Importer, Right side Decryptor & Result
        split_frame = ttk.Frame(container, style="TFrame")
        split_frame.pack(fill=tk.BOTH, expand=True)

        left_scan_card = tk.Frame(split_frame, bg=THEME["bg_card"], padx=18, pady=16)
        left_scan_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 15))

        right_decrypt_card = tk.Frame(split_frame, bg=THEME["bg_card"], padx=18, pady=16, width=420)
        right_decrypt_card.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_decrypt_card.pack_propagate(False)

        # Tabbed interface for Mode A (Import File) and Mode B (Webcam)
        tabs = ttk.Notebook(left_scan_card)
        tabs.pack(fill=tk.BOTH, expand=True)

        tab_import = ttk.Frame(tabs, style="Card.TFrame")
        tab_webcam = ttk.Frame(tabs, style="Card.TFrame")

        tabs.add(tab_import, text="  Import QR Image  ")
        tabs.add(tab_webcam, text="  Live Webcam  ")

        # --- TAB A: IMPORT IMAGE ---
        tk.Label(tab_import, text="Import QR Code File", font=(THEME["font_family"], 10, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(10, 6))

        file_btn_row = ttk.Frame(tab_import, style="Card.TFrame")
        file_btn_row.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(file_btn_row, text="Select QR Image File (PNG, JPG, BMP)...", style="Primary.TButton", command=self._handle_import_qr_image).pack(side=tk.LEFT)

        self.lbl_import_preview_box = tk.Frame(tab_import, bg=THEME["bg_input"], height=200, bd=1, relief="flat")
        self.lbl_import_preview_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.lbl_import_preview_box.pack_propagate(False)

        self.lbl_imported_img = tk.Label(self.lbl_import_preview_box, text="No image selected yet.", font=(THEME["font_family"], 9), fg=THEME["text_disabled"], bg=THEME["bg_input"])
        self.lbl_imported_img.pack(fill=tk.BOTH, expand=True)

        # --- TAB B: LIVE WEBCAM ---
        tk.Label(tab_webcam, text="Live Webcam Scanner", font=(THEME["font_family"], 10, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(10, 6))

        cam_btn_row = ttk.Frame(tab_webcam, style="Card.TFrame")
        cam_btn_row.pack(fill=tk.X, pady=(0, 8))

        self.btn_cam_toggle = ttk.Button(cam_btn_row, text="Start Camera", style="Primary.TButton", command=self._toggle_webcam)
        self.btn_cam_toggle.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_cam_status = tk.Label(cam_btn_row, text="Camera stopped", font=(THEME["font_family"], 8), fg=THEME["text_secondary"], bg=THEME["bg_card"])
        self.lbl_cam_status.pack(side=tk.LEFT)

        self.cam_feed_box = tk.Frame(tab_webcam, bg=THEME["bg_input"], height=200, bd=1, relief="flat")
        self.cam_feed_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.cam_feed_box.pack_propagate(False)

        self.lbl_cam_frame = tk.Label(self.cam_feed_box, text="Live camera stream will appear here.", font=(THEME["font_family"], 9), fg=THEME["text_disabled"], bg=THEME["bg_input"])
        self.lbl_cam_frame.pack(fill=tk.BOTH, expand=True)

        # Tab change event: stop webcam if tab A is selected
        tabs.bind("<<NotebookTabChanged>>", lambda e: self._on_scanner_tab_changed(tabs))

        # --- RIGHT CARD: DECRYPTION & UNLOCK ---
        tk.Label(right_decrypt_card, text="Note Decryption", font=(THEME["font_family"], 11, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 10))

        # Payload status card
        self.scanned_payload_str: Optional[str] = None
        self.scanned_payload_dict: Optional[Dict[str, Any]] = None

        self.lbl_scan_meta = tk.Label(
            right_decrypt_card,
            text="Scan or import a QR code to read its encrypted payload.",
            font=(THEME["font_family"], 9),
            fg=THEME["text_secondary"],
            bg=THEME["bg_card"],
            justify="left"
        )
        self.lbl_scan_meta.pack(anchor="w", pady=(0, 12))

        # Password entry
        tk.Label(right_decrypt_card, text="Enter Password to Decrypt:", font=(THEME["font_family"], 9, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(anchor="w")
        pwd_box = ttk.Frame(right_decrypt_card, style="Card.TFrame")
        pwd_box.pack(fill=tk.X, pady=(4, 12))

        self.entry_decrypt_pass = tk.Entry(pwd_box, show="*", bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat")
        self.entry_decrypt_pass.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry_decrypt_pass.bind("<Return>", lambda e: self._handle_decrypt_note())

        self.btn_decrypt = ttk.Button(right_decrypt_card, text="Decrypt & Read Note", style="Primary.TButton", command=self._handle_decrypt_note, state=tk.DISABLED)
        self.btn_decrypt.pack(fill=tk.X, pady=(0, 14))

        # Decrypted Results Display
        tk.Label(right_decrypt_card, text="Decrypted Note Content", font=(THEME["font_family"], 10, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 4))

        self.lbl_decrypted_title = tk.Label(right_decrypt_card, text="Title: ---", font=(THEME["font_family"], 10, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"], anchor="w")
        self.lbl_decrypted_title.pack(fill=tk.X)

        self.lbl_decrypted_cat = tk.Label(right_decrypt_card, text="Category: ---", font=(THEME["font_family"], 8), fg=THEME["text_secondary"], bg=THEME["bg_card"], anchor="w")
        self.lbl_decrypted_cat.pack(fill=tk.X, pady=(0, 6))

        self.txt_decrypted_content = tk.Text(right_decrypt_card, height=6, bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat", wrap="word", state=tk.DISABLED)
        self.txt_decrypted_content.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

    def _on_scanner_tab_changed(self, notebook: ttk.Notebook) -> None:
        idx = notebook.index(notebook.select())
        if idx == 0:  # Image tab
            self._stop_webcam()

    def _handle_import_qr_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Encrypted QR Code Image",
            initialdir=str(EXPORTS_DIR),
            filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")]
        )
        if not path:
            return

        try:
            self.set_status(f"Decoding QR from {Path(path).name}...")
            # Load and display thumbnail
            pil_img = Image.open(path)
            thumb = pil_img.copy()
            thumb.thumbnail((180, 180), Image.Resampling.LANCZOS)
            self.import_thumb_photo = ImageTk.PhotoImage(thumb)
            self.lbl_imported_img.config(image=self.import_thumb_photo, text="")

            # Decode QR string
            raw_payload = qr_manager.decode_qr_from_image(path)
            self._load_detected_payload(raw_payload)
            self.set_status("QR code decoded successfully. Enter password to unlock.")
        except Exception as e:
            logger.warning("Failed to decode QR image: %s", str(e))
            self.set_status("QR decode failed.", is_error=True)
            messagebox.showerror("QR Decode Failed", str(e))

    def _toggle_webcam(self) -> None:
        if self.scanner.is_running:
            self._stop_webcam()
        else:
            self._start_webcam()

    def _start_webcam(self) -> None:
        if not self.scanner.is_camera_available():
            messagebox.showerror(
                "Camera Unavailable",
                "No supported webcam or camera driver detected. Please check permissions or import an image file instead."
            )
            return

        success = self.scanner.start()
        if not success:
            messagebox.showerror("Camera Error", "Failed to access webcam.")
            return

        self.btn_cam_toggle.config(text="Stop Camera", style="Danger.TButton")
        self.lbl_cam_status.config(text="Camera active - scanning for QR...", fg=THEME["success"])
        self.set_status("Camera scanner running...")
        self._webcam_stream_loop()

    def _stop_webcam(self) -> None:
        if self.webcam_job:
            try:
                self.root.after_cancel(self.webcam_job)
            except Exception:
                pass
            self.webcam_job = None
        self.scanner.stop()
        if hasattr(self, "btn_cam_toggle"):
            try:
                if self.btn_cam_toggle.winfo_exists():
                    self.btn_cam_toggle.config(text="Start Camera", style="Primary.TButton")
                if hasattr(self, "lbl_cam_status") and self.lbl_cam_status.winfo_exists():
                    self.lbl_cam_status.config(text="Camera stopped", fg=THEME["text_secondary"])
                if hasattr(self, "lbl_cam_frame") and self.lbl_cam_frame.winfo_exists():
                    self.lbl_cam_frame.config(image="", text="Live camera stream will appear here.")
            except Exception:
                pass

    def _webcam_stream_loop(self) -> None:
        if not self.scanner.is_running:
            return

        ret, frame_bgr, detected_payload = self.scanner.read_frame()
        if ret and frame_bgr is not None:
            # Resize frame for UI preview box
            h, w = frame_bgr.shape[:2]
            target_w = 320
            target_h = int(h * (target_w / w))
            resized = cv2.resize(frame_bgr, (target_w, target_h))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            self.webcam_photo = ImageTk.PhotoImage(pil_img)
            self.lbl_cam_frame.config(image=self.webcam_photo, text="")

            if detected_payload:
                self._stop_webcam()
                self._load_detected_payload(detected_payload)
                self.set_status("QR Code detected by camera! Enter password to unlock.")
                messagebox.showinfo("QR Code Detected", "QR code detected from webcam stream! Please enter the password to decrypt.")
                return

        self.webcam_job = self.root.after(30, self._webcam_stream_loop)

    def _load_detected_payload(self, raw_payload_str: str) -> None:
        """Parses and validates payload metadata and activates the password prompt."""
        try:
            payload_dict = json.loads(raw_payload_str)
            encryption.validate_payload_structure(payload_dict)

            self.scanned_payload_str = raw_payload_str
            self.scanned_payload_dict = payload_dict

            uuid_val = payload_dict.get("uuid", "Unknown")
            alg_val = payload_dict.get("alg", "AES-256-GCM")
            kdf_val = payload_dict.get("kdf", {}).get("name", "Unknown")
            created_val = payload_dict.get("created_at", "Unknown")

            self.lbl_scan_meta.config(
                text=(
                    f"Status: Encrypted Payload Verified\n"
                    f"UUID: {uuid_val}\n"
                    f"Algorithm: {alg_val}\n"
                    f"KDF: {kdf_val}\n"
                    f"Created: {created_val}"
                ),
                fg=THEME["success"]
            )
            self.btn_decrypt.config(state=tk.NORMAL)
            self.entry_decrypt_pass.delete(0, tk.END)
            self.entry_decrypt_pass.focus_set()

        except Exception as e:
            self.scanned_payload_str = None
            self.scanned_payload_dict = None
            self.lbl_scan_meta.config(text=f"Invalid payload: {str(e)}", fg=THEME["danger"])
            self.btn_decrypt.config(state=tk.DISABLED)
            messagebox.showerror("Invalid Payload", f"The scanned QR code is not a valid QR Secure Notes payload:\n{str(e)}")

    def _handle_decrypt_note(self) -> None:
        if not self.scanned_payload_dict and not self.scanned_payload_str:
            return

        password = self.entry_decrypt_pass.get()
        if not password:
            messagebox.showwarning("Input Required", "Please enter the password to decrypt this note.")
            return

        try:
            self.set_status("Verifying password and decrypting...")
            self.root.update_idletasks()

            decrypted = self.note_mgr.unlock_payload(self.scanned_payload_str, password)

            # Update decrypted view
            title = decrypted.get("title", "Untitled Note")
            content = decrypted.get("content", "")
            cat = decrypted.get("category", "General")
            is_expired = decrypted.get("is_expired", False)

            self.lbl_decrypted_title.config(text=f"Title: {title}")
            exp_text = " [EXPIRED]" if is_expired else ""
            self.lbl_decrypted_cat.config(text=f"Category: {cat}{exp_text}", fg=THEME["warning"] if is_expired else THEME["text_secondary"])

            self.txt_decrypted_content.config(state=tk.NORMAL)
            self.txt_decrypted_content.delete("1.0", tk.END)
            self.txt_decrypted_content.insert("1.0", content)
            self.txt_decrypted_content.config(state=tk.DISABLED)

            self.entry_decrypt_pass.delete(0, tk.END)
            self.set_status("Note decrypted successfully.")

            if is_expired:
                messagebox.showwarning(
                    "Note Expired",
                    "This note has passed its designated expiration timestamp.\n\n"
                    "Note that portable QR codes can still be decrypted mathematically by anyone holding the correct password."
                )

        except encryption.DecryptionFailedError as dfe:
            self.set_status("Decryption failed: Incorrect password or tampered payload.", is_error=True)
            messagebox.showerror(
                "Decryption Failed",
                "Unable to unlock this note.\n\n"
                "Please verify your password and ensure the QR code image has not been damaged or tampered with."
            )
        except Exception as e:
            logger.error("Unexpected decryption error: %s", str(e))
            self.set_status("Decryption failed.", is_error=True)
            messagebox.showerror("Decryption Error", "Unable to unlock this note. Check the password or QR code.")

    # =========================================================================
    # VIEW 4: MY NOTES (DATABASE MANAGEMENT)
    # =========================================================================
    def _render_my_notes(self) -> None:
        container = ttk.Frame(self.content_area, style="TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        header = ttk.Label(container, text="My Encrypted Notes", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(container, text="Manage encrypted notes stored in local SQLite database (secure_notes.db).", style="Subheader.TLabel")
        sub.pack(anchor="w", pady=(2, 12))

        # Filter & Search Bar
        filter_bar = tk.Frame(container, bg=THEME["bg_card"], padx=14, pady=12)
        filter_bar.pack(fill=tk.X, pady=(0, 12))

        # Search box
        tk.Label(filter_bar, text="Search UUID/Category:", font=(THEME["font_family"], 9), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))
        self.entry_search = tk.Entry(filter_bar, bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 9), bd=1, relief="flat", width=20)
        self.entry_search.pack(side=tk.LEFT, padx=(0, 14), ipady=3)
        self.entry_search.bind("<Return>", lambda e: self._load_notes_table())

        # Status filter
        tk.Label(filter_bar, text="Status:", font=(THEME["font_family"], 9), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))
        self.combo_filter_status = ttk.Combobox(filter_bar, values=["all", "active", "expired"], width=10)
        self.combo_filter_status.current(0)
        self.combo_filter_status.pack(side=tk.LEFT, padx=(0, 14))
        self.combo_filter_status.bind("<<ComboboxSelected>>", lambda e: self._load_notes_table())

        # Category filter
        tk.Label(filter_bar, text="Category:", font=(THEME["font_family"], 9), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(side=tk.LEFT, padx=(0, 6))
        categories = ["all"] + database.get_categories(self.note_mgr.db_path)
        self.combo_filter_category = ttk.Combobox(filter_bar, values=categories, width=12)
        self.combo_filter_category.current(0)
        self.combo_filter_category.pack(side=tk.LEFT, padx=(0, 14))
        self.combo_filter_category.bind("<<ComboboxSelected>>", lambda e: self._load_notes_table())

        ttk.Button(filter_bar, text="Apply Filter", style="Secondary.TButton", command=self._load_notes_table).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(filter_bar, text="Refresh", style="Secondary.TButton", command=self._reset_notes_filter).pack(side=tk.LEFT)

        # Notes Table Card
        table_card = tk.Frame(container, bg=THEME["bg_card"], padx=14, pady=12)
        table_card.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        cols = ("id", "uuid", "category", "created_at", "expires_at", "status")
        self.tree_notes = ttk.Treeview(table_card, columns=cols, show="headings", height=10)
        self.tree_notes.heading("id", text="# ID")
        self.tree_notes.heading("uuid", text="Note Identifier (UUID)")
        self.tree_notes.heading("category", text="Category")
        self.tree_notes.heading("created_at", text="Created (Local)")
        self.tree_notes.heading("expires_at", text="Expires (Local)")
        self.tree_notes.heading("status", text="Status")

        self.tree_notes.column("id", width=50, anchor="center")
        self.tree_notes.column("uuid", width=200)
        self.tree_notes.column("category", width=110)
        self.tree_notes.column("created_at", width=160)
        self.tree_notes.column("expires_at", width=160)
        self.tree_notes.column("status", width=90, anchor="center")

        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.tree_notes.yview)
        self.tree_notes.configure(yscrollcommand=scrollbar.set)

        self.tree_notes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Action Toolbar below Table
        act_bar = tk.Frame(container, bg=THEME["bg_card"], padx=14, pady=12)
        act_bar.pack(fill=tk.X)

        ttk.Button(act_bar, text="Unlock / View Note", style="Primary.TButton", command=self._unlock_selected_note).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(act_bar, text="Export QR Code (PNG)...", style="Secondary.TButton", command=self._export_selected_note_qr).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(act_bar, text="Export Encrypted JSON...", style="Secondary.TButton", command=self._export_selected_note_json).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(act_bar, text="Delete Note", style="Danger.TButton", command=self._delete_selected_note).pack(side=tk.RIGHT)

        # Informational note
        info_lbl = tk.Label(
            container,
            text="Note: Titles and secret bodies remain encrypted in the database. Deleting a database record does not revoke exported QR codes.",
            font=(THEME["font_family"], 8),
            fg=THEME["text_secondary"],
            bg=THEME["bg_dark"]
        )
        info_lbl.pack(anchor="w", pady=(6, 0))

        # Initial load
        self._load_notes_table()

    def _reset_notes_filter(self) -> None:
        self.entry_search.delete(0, tk.END)
        self.combo_filter_status.current(0)
        self.combo_filter_category.current(0)
        self._load_notes_table()

    def _load_notes_table(self) -> None:
        for row in self.tree_notes.get_children():
            self.tree_notes.delete(row)

        sq = self.entry_search.get().strip() if hasattr(self, "entry_search") else None
        st = self.combo_filter_status.get() if hasattr(self, "combo_filter_status") else "all"
        cat = self.combo_filter_category.get() if hasattr(self, "combo_filter_category") else "all"

        notes = database.list_notes(
            search_query=sq,
            category=cat,
            status=st,
            db_path=self.note_mgr.db_path
        )

        for n in notes:
            # Format creation date to local time
            try:
                dt_c = datetime.fromisoformat(n["created_at"]).astimezone()
                c_str = dt_c.strftime("%Y-%m-%d %H:%M")
            except Exception:
                c_str = n["created_at"]

            # Format expiration date
            exp_raw = n.get("expires_at")
            if exp_raw:
                try:
                    dt_e = datetime.fromisoformat(exp_raw).astimezone()
                    e_str = dt_e.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    e_str = exp_raw
            else:
                e_str = "None"

            self.tree_notes.insert(
                "",
                tk.END,
                values=(
                    n["id"],
                    n["note_uuid"],
                    n["category"],
                    c_str,
                    e_str,
                    n["status"].upper()
                )
            )
        self.set_status(f"Loaded {len(notes)} note records from database.")

    def _get_selected_note_id(self) -> Optional[int]:
        selected = self.tree_notes.selection()
        if not selected:
            messagebox.showinfo("Selection Required", "Please select a note from the table first.")
            return None
        item = self.tree_notes.item(selected[0])
        return int(item["values"][0])

    def _unlock_selected_note(self) -> None:
        note_id = self._get_selected_note_id()
        if not note_id:
            return

        note = database.get_note_by_id(note_id, db_path=self.note_mgr.db_path)
        if not note:
            messagebox.showerror("Error", "Note not found in database.")
            return

        # Prompt for password via custom dialog
        pwd_dialog = PasswordPromptDialog(self.root, title=f"Unlock Note (UUID: {note['note_uuid'][:8]})")
        password = pwd_dialog.result
        if not password:
            return

        try:
            decrypted = self.note_mgr.unlock_payload(note["encrypted_payload"], password)
            DecryptedViewerDialog(self.root, decrypted)
        except encryption.DecryptionFailedError:
            messagebox.showerror("Unlock Failed", "Unable to unlock this note. Incorrect password.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to decrypt note: {str(e)}")

    def _export_selected_note_qr(self) -> None:
        note_id = self._get_selected_note_id()
        if not note_id:
            return

        note = database.get_note_by_id(note_id, db_path=self.note_mgr.db_path)
        if not note:
            return

        default_fn = qr_manager.get_default_export_filename(note["note_uuid"])
        path = filedialog.asksaveasfilename(
            initialdir=str(EXPORTS_DIR),
            initialfile=default_fn,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")]
        )
        if path:
            try:
                self.note_mgr.export_saved_note_qr(note_id, path)
                self.set_status(f"QR code exported: {Path(path).name}")
                messagebox.showinfo("Export Successful", f"QR code exported successfully to:\n{path}")
            except Exception as e:
                messagebox.showerror("Export Failed", str(e))

    def _export_selected_note_json(self) -> None:
        note_id = self._get_selected_note_id()
        if not note_id:
            return

        note = database.get_note_by_id(note_id, db_path=self.note_mgr.db_path)
        if not note:
            return

        default_fn = f"encrypted_note_{note['note_uuid'][:8]}.json"
        path = filedialog.asksaveasfilename(
            initialdir=str(EXPORTS_DIR),
            initialfile=default_fn,
            defaultextension=".json",
            filetypes=[("JSON File", "*.json")]
        )
        if path:
            try:
                self.note_mgr.export_saved_note_payload(note_id, path)
                self.set_status(f"Encrypted payload exported: {Path(path).name}")
                messagebox.showinfo("Export Successful", f"Encrypted payload JSON saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Export Failed", str(e))

    def _delete_selected_note(self) -> None:
        note_id = self._get_selected_note_id()
        if not note_id:
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            "Are you sure you want to delete this note from the database?\n\n"
            "This action cannot be undone.\n"
            "(Note: Exported PNG QR code images in other locations will remain intact.)",
            icon="warning"
        )
        if confirm:
            database.delete_note(note_id, hard_delete=True, db_path=self.note_mgr.db_path)
            self._load_notes_table()
            self.set_status("Note deleted from database.")

    # =========================================================================
    # VIEW 5: SECURITY & HELP
    # =========================================================================
    def _render_security_help(self) -> None:
        container = ttk.Frame(self.content_area, style="TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        header = ttk.Label(container, text="Security Architecture & Help Guide", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(container, text="Understanding the cryptographic foundation, key derivation, and offline safeguards.", style="Subheader.TLabel")
        sub.pack(anchor="w", pady=(2, 12))

        # Scrollable content area
        canvas = tk.Canvas(container, bg=THEME["bg_dark"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        scroll_content = ttk.Frame(canvas, style="TFrame")

        scroll_content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_content, anchor="nw", width=800)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Cards inside Help
        def make_help_card(parent, title: str, body_text: str):
            f = tk.Frame(parent, bg=THEME["bg_card"], padx=18, pady=16)
            f.pack(fill=tk.X, pady=(0, 14))
            tk.Label(f, text=title, font=(THEME["font_family"], 11, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 6))
            tk.Label(f, text=body_text, font=(THEME["font_family"], 9), fg=THEME["text_primary"], bg=THEME["bg_card"], justify="left", wraplength=760).pack(anchor="w")

        make_help_card(
            scroll_content,
            "1. Cryptographic Workflow",
            "• Encryption:\n"
            "   Plaintext Note  ──>  Argon2id (Salt + Password)  ──>  256-bit Key\n"
            "   Key + Unique Nonce + Plaintext  ──>  AES-256-GCM  ──>  Ciphertext + Auth Tag\n"
            "   Packaged into Versioned JSON Payload  ──>  Standard QR Code (PNG)\n\n"
            "• Decryption:\n"
            "   QR Code Image / Camera  ──>  Payload Validation  ──>  Password Entry\n"
            "   Argon2id Key Derivation  ──>  AES-GCM Authenticated Decryption  ──>  Plaintext Note"
        )

        make_help_card(
            scroll_content,
            "2. Why AES-256-GCM (Authenticated Encryption)?",
            "AES-GCM is an Authenticated Encryption with Associated Data (AEAD) cipher. "
            "Unlike older modes such as AES-CBC or AES-ECB, GCM computes a cryptographic 128-bit authentication tag. "
            "If an attacker alters even a single bit of the QR code ciphertext, the authentication tag verification fails immediately, "
            "preventing padding oracle attacks and bit-flipping tampering."
        )

        make_help_card(
            scroll_content,
            "3. Argon2id Key Derivation & Random Salts",
            "Passphrases cannot be used directly as cryptographic keys because humans choose low-entropy passwords. "
            "Argon2id (winner of the Password Hashing Competition) applies memory-hard and compute-hard functions (64MB RAM, 2 iterations) "
            "that resist GPU and ASIC brute-force cracking. Each encryption generates a fresh 16-byte cryptographically secure salt, "
            "ensuring two notes encrypted with the exact same password produce totally different keys and ciphertexts."
        )

        make_help_card(
            scroll_content,
            "4. Why Forgotten Passwords Cannot Be Recovered",
            "QR Secure Notes implements true zero-knowledge encryption. There is no backdoor, no master password, and no recovery server. "
            "Your password is never stored anywhere on your computer or in the database. "
            "If you lose your password, the ciphertext cannot be decrypted."
        )

        make_help_card(
            scroll_content,
            "5. Portable QR Codes vs. Remote Revocation",
            "Self-contained QR codes hold the entire encrypted payload within the graphic itself. "
            "Once an encrypted QR code is printed or exported, it cannot be remotely deleted or revoked over the air. "
            "Setting an expiration timestamp marks the note as expired in the database and warns the reader upon unlock, "
            "but anyone possessing the physical QR image and the password can still decrypt the math offline."
        )

        make_help_card(
            scroll_content,
            "6. Security Boundaries & Limitations",
            "• What this app protects: Confidentiality of notes stored at rest, protection against database theft, and tamper-detection during QR transport.\n"
            "• What is outside protection: Active keyloggers on the operating system, screen recording spyware, or camera eavesdropping while passwords are typed."
        )

    # =========================================================================
    # VIEW 6: SETTINGS & DATABASE BACKUP
    # =========================================================================
    def _render_settings(self) -> None:
        container = ttk.Frame(self.content_area, style="TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=25, pady=20)

        header = ttk.Label(container, text="Application Settings & Diagnostics", style="Header.TLabel")
        header.pack(anchor="w")
        sub = ttk.Label(container, text="Database management, backup tools, and cryptographic engine status.", style="Subheader.TLabel")
        sub.pack(anchor="w", pady=(2, 16))

        # DB Management Card
        db_card = tk.Frame(container, bg=THEME["bg_card"], padx=18, pady=16)
        db_card.pack(fill=tk.X, pady=(0, 16))

        tk.Label(db_card, text="SQLite Database Management", font=(THEME["font_family"], 11, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 6))

        db_size_kb = DB_PATH.stat().st_size / 1024 if DB_PATH.exists() else 0
        info_text = (
            f"Database File: {DB_PATH.resolve()}\n"
            f"File Size: {db_size_kb:.1f} KB\n"
            f"Engine: SQLite 3 (Built-in Python sqlite3 module)"
        )
        tk.Label(db_card, text=info_text, font=(THEME["font_family"], 9), fg=THEME["text_primary"], bg=THEME["bg_card"], justify="left").pack(anchor="w", pady=(0, 12))

        btn_row = ttk.Frame(db_card, style="Card.TFrame")
        btn_row.pack(anchor="w")

        ttk.Button(btn_row, text="Create Database Backup (.db)...", style="Primary.TButton", command=self._handle_database_backup).pack(side=tk.LEFT, padx=(0, 10))

        # Diagnostic Engine Card
        diag_card = tk.Frame(container, bg=THEME["bg_card"], padx=18, pady=16)
        diag_card.pack(fill=tk.X, pady=(0, 16))

        tk.Label(diag_card, text="Cryptographic & Hardware Diagnostics", font=(THEME["font_family"], 11, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_card"]).pack(anchor="w", pady=(0, 6))

        cam_ok = qr_manager.WebcamScanner.is_camera_available()
        argon_status = "Available (Argon2id Hardware Acceleration Enabled)" if encryption.HAS_ARGON2 else "Fallback Active (Scrypt Standard KDF)"

        diag_text = (
            f"• Authenticated Encryption: AES-256-GCM (Active)\n"
            f"• Key Derivation Engine: {argon_status}\n"
            f"• OpenCV Computer Vision: Active (v{cv2.__version__})\n"
            f"• Webcam Status: {'Camera detected and ready' if cam_ok else 'No webcam detected (Image mode active)'}\n"
            f"• Session QR Codes Generated: {self.note_mgr.session_qr_generated_count}"
        )
        tk.Label(diag_card, text=diag_text, font=(THEME["font_family"], 9), fg=THEME["text_primary"], bg=THEME["bg_card"], justify="left").pack(anchor="w")

        # Session Reset
        reset_box = ttk.Frame(diag_card, style="Card.TFrame")
        reset_box.pack(anchor="w", pady=(10, 0))
        ttk.Button(reset_box, text="Reset Session QR Counter", style="Secondary.TButton", command=self._reset_session_counter).pack(side=tk.LEFT)

    def _handle_database_backup(self) -> None:
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_backup = f"secure_notes_backup_{now_str}.db"
        dest_path = filedialog.asksaveasfilename(
            initialdir=str(DB_PATH.parent),
            initialfile=default_backup,
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db")]
        )
        if dest_path:
            try:
                database.backup_database(dest_path, db_path=self.note_mgr.db_path)
                self.set_status("Database backup completed.")
                messagebox.showinfo("Backup Successful", f"Full database backup written successfully to:\n{dest_path}")
            except Exception as e:
                messagebox.showerror("Backup Failed", str(e))

    def _reset_session_counter(self) -> None:
        self.note_mgr.session_qr_generated_count = 0
        self.set_status("Session QR counter reset.")
        self._show_view("settings")

    def on_close(self) -> None:
        """Gracefully release camera and close application."""
        self._stop_webcam()
        self.root.destroy()


# =============================================================================
# MODAL DIALOGS
# =============================================================================
class PasswordPromptDialog(tk.Toplevel):
    """Clean modal dialog to prompt for password."""

    def __init__(self, parent: tk.Tk, title: str = "Enter Password"):
        super().__init__(parent)
        self.title(title)
        self.geometry("380x180")
        self.resizable(False, False)
        self.configure(bg=THEME["bg_card"])
        self.transient(parent)
        self.grab_set()

        self.result: Optional[str] = None

        tk.Label(self, text=title, font=(THEME["font_family"], 11, "bold"), fg=THEME["text_primary"], bg=THEME["bg_card"]).pack(pady=(16, 8))

        self.entry = tk.Entry(self, show="*", bg=THEME["bg_input"], fg="#ffffff", insertbackground="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat", width=30)
        self.entry.pack(pady=(0, 16), ipady=4)
        self.entry.focus_set()
        self.entry.bind("<Return>", lambda e: self._on_ok())

        btn_row = ttk.Frame(self, style="Card.TFrame")
        btn_row.pack()

        ttk.Button(btn_row, text="Unlock", style="Primary.TButton", command=self._on_ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_row, text="Cancel", style="Secondary.TButton", command=self._on_cancel).pack(side=tk.LEFT, padx=6)

        self.wait_window(self)

    def _on_ok(self) -> None:
        self.result = self.entry.get()
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


class DecryptedViewerDialog(tk.Toplevel):
    """Clean modal dialog to view decrypted note content."""

    def __init__(self, parent: tk.Tk, note_dict: Dict[str, Any]):
        super().__init__(parent)
        self.title(f"Unlocked Note: {note_dict.get('title', 'Untitled')}")
        self.geometry("540x420")
        self.configure(bg=THEME["bg_card"])
        self.transient(parent)
        self.grab_set()

        title = note_dict.get("title", "Untitled Note")
        content = note_dict.get("content", "")
        cat = note_dict.get("category", "General")
        is_expired = note_dict.get("is_expired", False)

        header_frame = tk.Frame(self, bg=THEME["bg_card"], padx=18, pady=14)
        header_frame.pack(fill=tk.X)

        tk.Label(header_frame, text=title, font=(THEME["font_family"], 14, "bold"), fg=THEME["accent_blue"], bg=THEME["bg_card"]).pack(anchor="w")

        exp_tag = " • [EXPIRED]" if is_expired else ""
        tk.Label(header_frame, text=f"Category: {cat}{exp_tag}", font=(THEME["font_family"], 9), fg=THEME["warning"] if is_expired else THEME["text_secondary"], bg=THEME["bg_card"]).pack(anchor="w", pady=(2, 0))

        content_frame = tk.Frame(self, bg=THEME["bg_card"], padx=18)
        content_frame.pack(fill=tk.BOTH, expand=True)

        txt = tk.Text(content_frame, bg=THEME["bg_input"], fg="#ffffff", font=(THEME["font_family"], 10), bd=1, relief="flat", wrap="word")
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert("1.0", content)
        txt.config(state=tk.DISABLED)

        btn_row = tk.Frame(self, bg=THEME["bg_card"], padx=18, pady=14)
        btn_row.pack(fill=tk.X)

        ttk.Button(btn_row, text="Copy Content", style="Secondary.TButton", command=lambda: self._copy(content)).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Close", style="Primary.TButton", command=self.destroy).pack(side=tk.RIGHT)

    def _copy(self, content: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("Copied", "Note text copied to clipboard.")
