"""
Note Manager service layer for QR Secure Notes.
Coordinates note creation, password strength evaluation, expiration handling,
decryption workflows, export jobs, and database synchronization.
"""

from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image

import encryption
import qr_manager
import database
from config import EXPORTS_DIR, DB_PATH, MAX_CONTENT_CHARS, logger
import pypdf
from fpdf import FPDF
from fpdf.enums import XPos, YPos


class PasswordStrength:
    """Evaluates password strength and entropy characteristics."""

    @staticmethod
    def evaluate(password: str) -> Dict[str, Any]:
        if not password:
            return {"score": 0, "label": "Empty", "color": "#64748b", "feedback": "Enter a password"}

        length = len(password)
        has_upper = bool(re.search(r"[A-Z]", password))
        has_lower = bool(re.search(r"[a-z]", password))
        has_digit = bool(re.search(r"\d", password))
        has_symbol = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password))

        score = 0
        if length >= 8:
            score += 25
        elif length >= 6:
            score += 15
        else:
            score += 5

        if length >= 12:
            score += 25
        elif length >= 10:
            score += 15

        char_variety = sum([has_upper, has_lower, has_digit, has_symbol])
        score += char_variety * 12.5

        score = min(100, int(score))

        if score < 35:
            return {"score": score, "label": "Weak", "color": "#ef4444", "feedback": "Use at least 8 chars with mixed cases & numbers"}
        elif score < 65:
            return {"score": score, "label": "Fair", "color": "#f59e0b", "feedback": "Add symbols or increase length for better protection"}
        elif score < 85:
            return {"score": score, "label": "Good", "color": "#3b82f6", "feedback": "Solid password strength"}
        else:
            return {"score": score, "label": "Strong", "color": "#10b981", "feedback": "Excellent cryptographic protection"}


class NoteManager:
    """Manages high-level note workflows and tracks application session state."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = db_path
        self.session_qr_generated_count: int = 0
        database.init_db(self.db_path)

    def calculate_expiration_timestamp(self, preset_or_custom: str) -> Optional[str]:
        """
        Calculates UTC ISO-8601 expiration timestamp from a preset option:
        'none', '1_hour', '24_hours', '7_days', '30_days', or custom ISO string.
        """
        if not preset_or_custom or preset_or_custom.lower() in ("none", "never", ""):
            return None

        now = datetime.now(timezone.utc)
        mapping = {
            "1_hour": timedelta(hours=1),
            "24_hours": timedelta(hours=24),
            "7_days": timedelta(days=7),
            "30_days": timedelta(days=30),
        }

        if preset_or_custom in mapping:
            return (now + mapping[preset_or_custom]).isoformat()

        # Try parsing as ISO format if custom string
        try:
            dt = datetime.fromisoformat(preset_or_custom)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat()
        except ValueError:
            raise ValueError(f"Invalid expiration date format: {preset_or_custom}")

    def create_secure_note(
        self,
        title: str,
        content: str,
        password: str,
        confirm_password: str,
        category: str = "General",
        expiration_option: str = "none",
        save_to_database: bool = True,
        auto_export_qr: bool = False,
        use_scrypt: bool = False
    ) -> Dict[str, Any]:
        """
        Validates inputs, encrypts the note, renders QR code, and handles storage & export.
        """
        if not content or not content.strip():
            raise ValueError("Note content cannot be empty.")

        if not password:
            raise ValueError("Password is required.")

        if password != confirm_password:
            raise ValueError("Passwords do not match. Please re-enter your password.")

        expires_at = self.calculate_expiration_timestamp(expiration_option)

        # Encrypt the note payload
        payload_dict, serialized_payload = encryption.encrypt_note(
            title=title,
            content=content,
            password=password,
            category=category,
            expires_at=expires_at,
            use_scrypt=use_scrypt
        )

        # Generate QR code image
        qr_img = qr_manager.generate_qr_image(serialized_payload)
        self.session_qr_generated_count += 1

        note_uuid = payload_dict["uuid"]
        saved_row_id = None
        auto_export_path = None

        if save_to_database:
            saved_row_id = database.insert_note(
                note_uuid=note_uuid,
                encrypted_payload=serialized_payload,
                category=category,
                expires_at=expires_at,
                db_path=self.db_path
            )

        if auto_export_qr:
            default_fn = qr_manager.get_default_export_filename(note_uuid)
            target_path = EXPORTS_DIR / default_fn
            auto_export_path = qr_manager.save_qr_image(qr_img, target_path)

        return {
            "uuid": note_uuid,
            "payload_dict": payload_dict,
            "serialized_payload": serialized_payload,
            "qr_image": qr_img,
            "row_id": saved_row_id,
            "auto_exported_path": auto_export_path,
            "expires_at": expires_at,
        }

    def unlock_payload(self, payload_or_json: Dict[str, Any] | str, password: str) -> Dict[str, Any]:
        """
        Unlocks and decrypts a note payload.
        Checks expiration and returns decrypted note dict with metadata.
        """
        decrypted_dict = encryption.decrypt_note(payload_or_json, password)

        # Check expiration status if expires_at was included
        is_expired = False
        expires_at_str = decrypted_dict.get("expires_at")
        if expires_at_str:
            try:
                exp_dt = datetime.fromisoformat(expires_at_str)
                now_utc = datetime.now(timezone.utc)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if now_utc > exp_dt:
                    is_expired = True
            except Exception:
                pass

        decrypted_dict["is_expired"] = is_expired
        return decrypted_dict

    def export_saved_note_qr(self, note_id: int, target_file_path: Path | str) -> Path:
        """Re-generates and exports the QR code of a previously saved note from the database."""
        note = database.get_note_by_id(note_id, db_path=self.db_path)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found in database.")

        qr_img = qr_manager.generate_qr_image(note["encrypted_payload"])
        saved_path = qr_manager.save_qr_image(qr_img, target_file_path)
        self.session_qr_generated_count += 1
        return saved_path

    def export_saved_note_payload(self, note_id: int, target_file_path: Path | str) -> Path:
        """Exports raw encrypted payload JSON to a file."""
        note = database.get_note_by_id(note_id, db_path=self.db_path)
        if not note:
            raise ValueError(f"Note with ID {note_id} not found in database.")

        path = Path(target_file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(note["encrypted_payload"])
        return path

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Gathers stats and recent notes for the dashboard view."""
        stats = database.get_dashboard_stats(self.db_path)
        stats["session_qr_generated"] = self.session_qr_generated_count
        recent_notes = database.list_notes(db_path=self.db_path)[:5]
        return {
            "stats": stats,
            "recent_notes": recent_notes
        }

    @staticmethod
    def extract_text_from_pdf(pdf_path: Path | str) -> Tuple[str, str]:
        """
        Extracts readable text from a selected PDF document.
        Returns:
            (suggested_title: str, extracted_content: str)
        """
        path = Path(pdf_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {path}")

        try:
            reader = pypdf.PdfReader(str(path))
            pages_text = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages_text.append(text.strip())

            full_text = "\n\n".join(pages_text).strip()
            if not full_text:
                raise ValueError("No readable text found in the selected PDF (it may contain only scanned images).")

            suggested_title = path.stem.replace("_", " ").title()
            return suggested_title, full_text
        except Exception as e:
            if isinstance(e, (FileNotFoundError, ValueError)):
                raise
            logger.error("Error reading PDF: %s", str(e))
            raise ValueError(f"Could not read PDF file: {str(e)}")

    @staticmethod
    def export_note_to_pdf(note_dict: Dict[str, Any], output_path: Path | str) -> Path:
        """
        Exports a decrypted note record into a formatted, high-quality PDF document.
        """
        path = Path(output_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        title = str(note_dict.get("title", "Untitled Note"))
        content = str(note_dict.get("content", ""))
        category = str(note_dict.get("category", "General"))
        created_at = str(note_dict.get("created_at", "N/A"))
        is_expired = note_dict.get("is_expired", False)

        # Sanitize for latin-1 core font support
        def clean_str(s: str) -> str:
            return s.encode("latin-1", "replace").decode("latin-1")

        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(18, 18, 18)
        pdf.add_page()

        # Header Banner
        pdf.set_fill_color(18, 30, 49)
        pdf.rect(18, 18, 174, 28, "F")

        pdf.set_xy(22, 22)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 8, "QR SECURE NOTES - DECRYPTED EXPORT", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_xy(22, 31)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(175, 200, 240)
        pdf.cell(0, 6, "Encrypted Storage - Zero-Knowledge Authenticated Document", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_y(52)

        # Metadata Card
        pdf.set_fill_color(245, 247, 250)
        pdf.set_draw_color(210, 220, 235)
        pdf.rect(18, 52, 174, 24, "DF")

        pdf.set_xy(22, 55)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(25, 40, 65)
        pdf.cell(20, 6, "Title:")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(100, 6, clean_str(title))
        pdf.ln(6)

        pdf.set_x(22)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(20, 6, "Category:")
        pdf.set_font("Helvetica", "", 9)
        status_tag = " [EXPIRED]" if is_expired else " [ACTIVE]"
        pdf.cell(50, 6, f"{clean_str(category)}{status_tag}")

        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(22, 6, "Created:")
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, clean_str(created_at), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_y(82)

        # Note Content Body
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(20, 70, 160)
        pdf.cell(0, 8, "Note Content:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(35, 40, 50)
        pdf.multi_cell(0, 5.2, clean_str(content))
        pdf.ln(10)

        # Security Watermark Footer
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(130, 140, 155)
        pdf.cell(0, 6, "Decrypted offline via QR Secure Notes - Authenticated AES-256-GCM / Argon2id", align="C")

        pdf.output(str(path))
        logger.info("Exported note to PDF at: %s", str(path))
        return path
