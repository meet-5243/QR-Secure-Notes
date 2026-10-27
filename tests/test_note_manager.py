"""
Unit tests for NoteManager service.
Verifies note creation flow, password strength evaluation, expiration timestamping,
unlocking, and export functionality.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from note_manager import NoteManager, PasswordStrength
import database

@pytest.fixture
def note_mgr(tmp_path: Path):
    test_db = tmp_path / "test_notes.db"
    return NoteManager(db_path=test_db)


def test_password_strength_evaluation():
    p_empty = PasswordStrength.evaluate("")
    assert p_empty["label"] == "Empty"
    assert p_empty["score"] == 0

    p_weak = PasswordStrength.evaluate("abc")
    assert p_weak["label"] == "Weak"

    p_strong = PasswordStrength.evaluate("Tr0ub4dor&3#2026!")
    assert p_strong["label"] in ("Good", "Strong")
    assert p_strong["score"] >= 75


def test_create_and_unlock_note(note_mgr: NoteManager):
    result = note_mgr.create_secure_note(
        title="Project Plan",
        content="Antigravity offline execution instructions",
        password="ValidPassword123!",
        confirm_password="ValidPassword123!",
        category="Development",
        save_to_database=True
    )

    assert result["uuid"] is not None
    assert result["row_id"] is not None
    assert result["qr_image"] is not None
    assert note_mgr.session_qr_generated_count == 1

    # Unlock payload
    unlocked = note_mgr.unlock_payload(result["serialized_payload"], "ValidPassword123!")
    assert unlocked["title"] == "Project Plan"
    assert unlocked["content"] == "Antigravity offline execution instructions"
    assert unlocked["category"] == "Development"
    assert unlocked["is_expired"] is False


def test_password_mismatch_error(note_mgr: NoteManager):
    with pytest.raises(ValueError, match="Passwords do not match"):
        note_mgr.create_secure_note(
            title="Mismatch",
            content="Some body",
            password="passA",
            confirm_password="passB"
        )


def test_expiration_calculation(note_mgr: NoteManager):
    ts_none = note_mgr.calculate_expiration_timestamp("none")
    assert ts_none is None

    ts_1h = note_mgr.calculate_expiration_timestamp("1_hour")
    assert ts_1h is not None
    dt = datetime.fromisoformat(ts_1h)
    assert dt > datetime.now(timezone.utc)


def test_export_saved_note_qr(note_mgr: NoteManager, tmp_path: Path):
    result = note_mgr.create_secure_note(
        title="To Export",
        content="Secret to export as QR",
        password="PassWord123!",
        confirm_password="PassWord123!",
        save_to_database=True
    )
    row_id = result["row_id"]

    target_export = tmp_path / "exported_note.png"
    saved = note_mgr.export_saved_note_qr(row_id, target_export)
    assert saved.exists()


def test_pdf_export_and_extraction(tmp_path: Path):
    note_data = {
        "title": "Confidential Research",
        "content": "Zero-Knowledge Encryption with AES-256-GCM and Argon2id.",
        "category": "Research",
        "created_at": "2026-10-27T12:00:00Z",
        "is_expired": False
    }

    # Test PDF Export
    pdf_out = tmp_path / "test_exported_note.pdf"
    exported_path = NoteManager.export_note_to_pdf(note_data, pdf_out)
    assert exported_path.exists()
    assert exported_path.stat().st_size > 0

    # Test PDF Text Extraction
    suggested_title, extracted_text = NoteManager.extract_text_from_pdf(exported_path)
    assert "Test Exported Note" in suggested_title or "Confidential" in suggested_title or len(suggested_title) > 0
    assert "AES-256-GCM" in extracted_text

