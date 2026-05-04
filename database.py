"""
database.py — SQLite persistence layer for DTNCV ATS
Manages the `job_descriptions` table (luu lich su JD).
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_PATH = os.getenv("DB_PATH", "ats_data.db")


# -----------------------------------------
#  Connection helper
# -----------------------------------------

def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# -----------------------------------------
#  Schema initialisation + auto-migration
# -----------------------------------------

def init_db() -> None:
    """Create tables and run column migrations. Called once at app startup."""
    with get_connection() as conn:
        # 1. Create table with full schema (no-op if already exists)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_descriptions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                title            TEXT    NOT NULL DEFAULT '',
                jd_text          TEXT    NOT NULL,
                jd_hash          TEXT    NOT NULL UNIQUE,
                pass_threshold   REAL    NOT NULL DEFAULT 70,
                review_threshold REAL    NOT NULL DEFAULT 50,
                created_at       TEXT    NOT NULL,
                updated_at       TEXT    NOT NULL
            )
        """)

        # 2. Auto-migration: add columns missing from older DB files
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(job_descriptions)").fetchall()
        }
        pending = [
            ("pass_threshold",   "REAL NOT NULL DEFAULT 70"),
            ("review_threshold", "REAL NOT NULL DEFAULT 50"),
            ("title",            "TEXT NOT NULL DEFAULT ''"),
            ("updated_at",       "TEXT NOT NULL DEFAULT ''"),
        ]
        for col, definition in pending:
            if col not in existing:
                conn.execute(
                    f"ALTER TABLE job_descriptions ADD COLUMN {col} {definition}"
                )
                print(f"[DB] Migration: added column '{col}'")

        conn.commit()
    print(f"[DB] SQLite ready: {os.path.abspath(DB_PATH)}")


# -----------------------------------------
#  CRUD — job_descriptions
# -----------------------------------------

def upsert_job_description(
    jd_text: str,
    jd_hash: str,
    title: str = "",
    pass_threshold: float = 70.0,
    review_threshold: float = 50.0,
) -> int:
    """
    Insert a new JD or update title/thresholds when the hash already exists.
    Returns the row id.
    """
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute(
            "SELECT id FROM job_descriptions WHERE jd_hash = ?", (jd_hash,)
        )
        row = cur.fetchone()

        if row:
            conn.execute(
                """
                UPDATE job_descriptions
                SET title = ?, pass_threshold = ?, review_threshold = ?, updated_at = ?
                WHERE jd_hash = ?
                """,
                (title, pass_threshold, review_threshold, now, jd_hash),
            )
            conn.commit()
            return row["id"]

        cur = conn.execute(
            """
            INSERT INTO job_descriptions
                (title, jd_text, jd_hash, pass_threshold, review_threshold,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, jd_text, jd_hash, pass_threshold, review_threshold, now, now),
        )
        conn.commit()
        return cur.lastrowid


def list_job_descriptions(limit: int = 50, offset: int = 0) -> list[dict]:
    """Return all saved JDs newest-first (preview only, no full jd_text)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, jd_hash, pass_threshold, review_threshold,
                   created_at, updated_at,
                   SUBSTR(jd_text, 1, 200) AS preview
            FROM job_descriptions
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def get_job_description(jd_id: int) -> Optional[dict]:
    """Return a single JD row by primary key, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM job_descriptions WHERE id = ?", (jd_id,)
        ).fetchone()
    return dict(row) if row else None


def get_job_description_by_hash(jd_hash: str) -> Optional[dict]:
    """Return a JD row by its MD5 hash, or None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM job_descriptions WHERE jd_hash = ?", (jd_hash,)
        ).fetchone()
    return dict(row) if row else None


def delete_job_description(jd_id: int) -> bool:
    """Delete a JD by id. Returns True if a row was deleted."""
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM job_descriptions WHERE id = ?", (jd_id,)
        )
        conn.commit()
    return cur.rowcount > 0
