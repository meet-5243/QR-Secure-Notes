"""
QR Secure Notes - Entry Point.
A Python-focused secure desktop application for encrypted notes and QR codes.
Launches the native Tkinter GUI and verifies runtime environment.
"""

import sys
import tkinter as tk
from tkinter import messagebox

from config import (
    APP_NAME,
    APP_VERSION,
    DB_PATH,
    logger,
)
import database
from ui import QRSecureNotesApp


def main() -> None:
    """Initializes the database and starts the desktop GUI application."""
    logger.info("Starting %s v%s...", APP_NAME, APP_VERSION)

    # 1. Initialize local SQLite database
    try:
        database.init_db(DB_PATH)
    except Exception as e:
        logger.critical("Fatal: Database initialization failed: %s", str(e))
        print(f"Error: Could not initialize database at {DB_PATH}: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Start Tkinter Root Window
    root = tk.Tk()
    root.title(f"{APP_NAME} v{APP_VERSION}")

    # Set minimum size
    root.minsize(980, 640)

    try:
        app = QRSecureNotesApp(root)
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Application terminated by user.")
    except Exception as e:
        logger.critical("Unhandled application error: %s", str(e), exc_info=True)
        messagebox.showerror(
            "Application Error",
            f"An unexpected error occurred:\n{str(e)}\n\nCheck logs for safe diagnostics."
        )


if __name__ == "__main__":
    main()
