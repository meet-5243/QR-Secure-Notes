"""
SQLite Database module for QR Secure Notes.
Provides schema management, parameterized CRUD operations, backup capabilities,
and automatic expiration tracking.
Stores strictly encrypted payloads without plaintext titles or secrets.
"""

from __future__ import annotations
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from config import DB_PATH, logger


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Creates and returns a connection to the SQLite database with Row factory."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Path | str = DB_PATH) -> None:
    """
    Initializes the database schema and required indexes.
    Idempotent and safe to run on existing databases.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note_uuid TEXT UNIQUE NOT NULL,
                encrypted_payload TEXT NOT NULL,
                category TEXT DEFAULT 'General',
                created_at TEXT NOT NULL,
                expires_at TEXT,
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'deleted')),
                updated_at TEXT NOT NULL
            );
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_uuid ON notes (note_uuid);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_status ON notes (status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes (created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_category ON notes (category);")
        conn.commit()
    logger.info("Database initialized successfully at: %s", str(db_path))


def refresh_expirations(conn: sqlite3.Connection) -> int:
    """
    Marks active notes whose expires_at timestamp has passed as 'expired'.
    Returns number of expired notes updated.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE notes
        SET status = 'expired', updated_at = ?
        WHERE status = 'active'
          AND expires_at IS NOT NULL
          AND expires_at <= ?
        """,
        (now_utc, now_utc)
    )
    conn.commit()
    return cursor.rowcount


def insert_note(
    note_uuid: str,
    encrypted_payload: str,
    category: str = "General",
    expires_at: Optional[str] = None,
    db_path: Path | str = DB_PATH
) -> int:
    """
    Inserts a newly encrypted note record into the database.
    Returns the newly inserted row ID.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO notes (
                note_uuid, encrypted_payload, category, created_at, expires_at, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
            (note_uuid, encrypted_payload, category, now_utc, expires_at, now_utc)
        )
        conn.commit()
        return cursor.lastrowid


def get_note_by_uuid(note_uuid: str, db_path: Path | str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves a note by its public UUID."""
    with get_connection(db_path) as conn:
        refresh_expirations(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM notes WHERE note_uuid = ?",
            (note_uuid,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_note_by_id(note_id: int, db_path: Path | str = DB_PATH) -> Optional[Dict[str, Any]]:
    """Retrieves a note by primary key ID."""
    with get_connection(db_path) as conn:
        refresh_expirations(conn)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM notes WHERE id = ?",
            (note_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def list_notes(
    search_query: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    include_deleted: bool = False,
    db_path: Path | str = DB_PATH
) -> List[Dict[str, Any]]:
    """
    Returns filtered and sorted note records.
    """
    with get_connection(db_path) as conn:
        refresh_expirations(conn)
        cursor = conn.cursor()

        query = "SELECT * FROM notes WHERE 1=1"
        params: List[Any] = []

        if not include_deleted and status != "deleted":
            query += " AND status != 'deleted'"

        if status and status != "all":
            query += " AND status = ?"
            params.append(status)

        if category and category != "all":
            query += " AND category = ?"
            params.append(category)

        if search_query and search_query.strip():
            sq = f"%{search_query.strip()}%"
            query += " AND (note_uuid LIKE ? OR category LIKE ?)"
            params.extend([sq, sq])

        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def delete_note(note_id: int, hard_delete: bool = True, db_path: Path | str = DB_PATH) -> bool:
    """
    Deletes a note record. Defaults to permanent hard delete.
    If hard_delete=False, updates status to 'deleted'.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if hard_delete:
            cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        else:
            now_utc = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                "UPDATE notes SET status = 'deleted', updated_at = ? WHERE id = ?",
                (now_utc, note_id)
            )
        conn.commit()
        return cursor.rowcount > 0


def get_categories(db_path: Path | str = DB_PATH) -> List[str]:
    """Returns a list of distinct categories currently present in the database."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM notes WHERE category IS NOT NULL ORDER BY category ASC")
        return [row[0] for row in cursor.fetchall() if row[0]]


def get_dashboard_stats(db_path: Path | str = DB_PATH) -> Dict[str, int]:
    """Returns real dashboard statistics directly from the database."""
    with get_connection(db_path) as conn:
        refresh_expirations(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM notes WHERE status != 'deleted'")
        total_notes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM notes WHERE status = 'active'")
        active_notes = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM notes WHERE status = 'expired'")
        expired_notes = cursor.fetchone()[0]

        return {
            "total_notes": total_notes,
            "active_notes": active_notes,
            "expired_notes": expired_notes,
        }


def backup_database(destination_path: Path | str, db_path: Path | str = DB_PATH) -> None:
    """
    Performs a live online backup of the SQLite database using SQLite's backup API.
    """
    dest = Path(destination_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as src_conn:
        with sqlite3.connect(str(dest)) as dest_conn:
            src_conn.backup(dest_conn)
    logger.info("Database backup created at: %s", str(dest))
