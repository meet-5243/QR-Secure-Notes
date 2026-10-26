"""
Configuration module for QR Secure Notes.
Defines paths, cryptographic defaults, UI constants, and logging setups.
"""

from pathlib import Path
import os
import logging

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = BASE_DIR / "exports"
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"

# Ensure runtime directories exist
for directory in (DATA_DIR, EXPORTS_DIR, ASSETS_DIR, LOGS_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = DATA_DIR / "secure_notes.db"

# Application metadata
APP_NAME = "QR Secure Notes"
APP_SUBTITLE = "Your secrets. Encrypted. Protected."
APP_VERSION = "1.0.0"

# Cryptographic configuration
PAYLOAD_VERSION = 1
ENCRYPTION_ALGORITHM = "AES-256-GCM"
KEY_SIZE_BYTES = 32          # 256 bits
GCM_NONCE_SIZE_BYTES = 12    # 96 bits standard for GCM
SALT_SIZE_BYTES = 16         # 128 bits

# Argon2id KDF parameters (balanced for desktop security and responsiveness)
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 65536   # 64 MiB
ARGON2_PARALLELISM = 2

# Scrypt fallback parameters
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1

# Note constraints
MAX_TITLE_CHARS = 100
MAX_CONTENT_CHARS = 1500     # Ensures reliable QR rendering within Version 25-30 QR capacities

# QR Generation parameters
QR_BOX_SIZE = 10
QR_BORDER = 4

# UI Dark Palette
THEME = {
    "bg_dark": "#0f141c",       # Deepest charcoal navy
    "bg_sidebar": "#161d2b",    # Sidebar & navigation
    "bg_card": "#1e2738",       # Elevated card panels
    "bg_card_alt": "#253147",   # Alternate card/detail background
    "bg_input": "#131924",      # Text inputs / entries
    "accent_blue": "#3b82f6",   # Primary accent
    "accent_hover": "#2563eb",  # Button hover
    "accent_violet": "#8b5cf6", # Secondary accent
    "text_primary": "#f8fafc",  # Main text
    "text_secondary": "#94a3b8",# Muted captions / subheadings
    "text_disabled": "#64748b", # Disabled elements
    "border": "#2d3748",        # Dividers and borders
    "success": "#10b981",       # Success indicators
    "warning": "#f59e0b",       # Warning badges
    "danger": "#ef4444",        # Error messages
    "font_family": "Segoe UI",  # Standard clean Windows font
}

def setup_logging() -> logging.Logger:
    """Configures safe application logging that avoids storing secrets."""
    log_file = LOGS_DIR / "qr_secure_notes.log"
    logger = logging.getLogger("QRSecureNotes")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

logger = setup_logging()
