"""
Unit tests for the database module.
Verifies table creation, parameterized queries, filtering, expiration transitions, and backup.
"""

import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
import database

@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_notes.db"
    database.init_db(db_file)
    return db_file


def test_init_db_idempotent(test_db):
    # Calling init_db again should not throw errors or wipe tables
    database.init_db(test_db)
    stats = database.get_dashboard_stats(test_db)
    assert stats["total_notes"] == 0


def test_insert_and_retrieve_note(test_db):
    uuid_val = "test-uuid-123"
    payload = '{"v":1,"alg":"AES-256-GCM"}'
    category = "Finance"

    row_id = database.insert_note(
        note_uuid=uuid_val,
        encrypted_payload=payload,
        category=category,
        db_path=test_db
    )
    assert row_id > 0

    note = database.get_note_by_uuid(uuid_val, db_path=test_db)
    assert note is not None
    assert note["note_uuid"] == uuid_val
    assert note["category"] == category
    assert note["status"] == "active"
    assert note["encrypted_payload"] == payload


def test_unique_uuid_constraint(test_db):
    uuid_val = "duplicate-uuid"
    database.insert_note(uuid_val, "payload1", db_path=test_db)

    with pytest.raises(sqlite3.IntegrityError):
        database.insert_note(uuid_val, "payload2", db_path=test_db)


def test_delete_note(test_db):
    row_id = database.insert_note("del-uuid", "payload", db_path=test_db)
    success = database.delete_note(row_id, hard_delete=True, db_path=test_db)
    assert success is True

    deleted_note = database.get_note_by_id(row_id, db_path=test_db)
    assert deleted_note is None


def test_expiration_status_update(test_db):
    past_utc = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    future_utc = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    database.insert_note("exp-uuid", "payload-exp", expires_at=past_utc, db_path=test_db)
    database.insert_note("act-uuid", "payload-act", expires_at=future_utc, db_path=test_db)

    stats = database.get_dashboard_stats(test_db)
    assert stats["total_notes"] == 2
    assert stats["active_notes"] == 1
    assert stats["expired_notes"] == 1


def test_backup_database(test_db, tmp_path: Path):
    database.insert_note("backup-uuid", "payload-backup", db_path=test_db)

    backup_file = tmp_path / "backup_notes.db"
    database.backup_database(backup_file, db_path=test_db)

    assert backup_file.exists()
    backup_note = database.get_note_by_uuid("backup-uuid", db_path=backup_file)
    assert backup_note is not None
    assert backup_note["note_uuid"] == "backup-uuid"
