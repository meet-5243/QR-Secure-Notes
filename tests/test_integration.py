"""
End-to-End Integration Tests for QR Secure Notes.
Verifies the complete flow: Note Creation -> Key Derivation -> AES-GCM Encryption ->
QR Code Generation -> PNG Export -> QR Image Decode -> Password Authentication -> Decryption.
"""

from pathlib import Path
from note_manager import NoteManager
import qr_manager
import database
import encryption


def test_full_roundtrip_workflow(tmp_path: Path):
    db_file = tmp_path / "integration_test.db"
    mgr = NoteManager(db_path=db_file)

    title = "Secret Exam Paper"
    content = "Question 1: Explain authenticated encryption with AES-GCM.\nQuestion 2: Discuss Argon2id."
    password = "MasterPassword2026!"
    category = "Academics"

    # 1. Create secure note
    result = mgr.create_secure_note(
        title=title,
        content=content,
        password=password,
        confirm_password=password,
        category=category,
        expiration_option="24_hours",
        save_to_database=True,
        auto_export_qr=False
    )

    assert result["uuid"] is not None
    assert result["row_id"] is not None
    assert mgr.session_qr_generated_count == 1

    # 2. Save QR image to disk
    qr_file = tmp_path / "generated_qr.png"
    qr_manager.save_qr_image(result["qr_image"], qr_file)
    assert qr_file.exists()

    # 3. Read & Decode QR image from file
    decoded_payload = qr_manager.decode_qr_from_image(qr_file)
    assert decoded_payload == result["serialized_payload"]

    # 4. Decrypt with correct password
    unlocked = mgr.unlock_payload(decoded_payload, password)
    assert unlocked["title"] == title
    assert unlocked["content"] == content
    assert unlocked["category"] == category
    assert unlocked["is_expired"] is False

    # 5. Verify database storage has no secrets in plaintext
    saved_note = database.get_note_by_id(result["row_id"], db_path=db_file)
    assert saved_note is not None
    # Check that plaintext title and content are NOT in the database row
    assert title not in saved_note["encrypted_payload"]
    assert content not in saved_note["encrypted_payload"]
    assert password not in saved_note["encrypted_payload"]

    # 6. Verify dashboard stats reflect the newly created note
    stats = database.get_dashboard_stats(db_path=db_file)
    assert stats["total_notes"] == 1
    assert stats["active_notes"] == 1
    assert stats["expired_notes"] == 0
