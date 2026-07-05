"""
Auth migration script — idempotent, safe to run multiple times.
Creates the 'users' table and adds 'created_by' to 'interview_sessions'.
Backfills existing sessions under a default admin user.
"""

import sqlite3
import os
import sys

# Resolve paths relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from config import settings  # noqa: E402

DB_PATH = os.path.abspath(settings.database_path)
ADMIN_EMAIL = settings.admin_email or "admin@interviewprep.local"  # nosec


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Create users table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email VARCHAR(255) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            picture VARCHAR(500),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ 'users' table ensured.")

    # 2. Add all missing columns to interview_sessions
    cursor.execute("PRAGMA table_info(interview_sessions)")
    columns = [col[1] for col in cursor.fetchall()]

    # Define all columns that may be missing from older databases
    missing_columns = {
        "job_description": "TEXT",
        "joined_at": "DATETIME",
        "created_by": "INTEGER REFERENCES users(id)",
    }

    for col_name, col_type in missing_columns.items():
        if col_name not in columns:
            cursor.execute(
                f"ALTER TABLE interview_sessions ADD COLUMN {col_name} {col_type}"
            )
            print(f"✅ '{col_name}' column added to interview_sessions.")
        else:
            print(f"ℹ️  '{col_name}' column already exists.")

    # 3. Create index for created_by if not exists
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_interview_sessions_created_by 
        ON interview_sessions(created_by)
    """)

    # 4. Backfill: create default admin user and assign orphan sessions
    cursor.execute("SELECT id FROM users WHERE email = ?", (ADMIN_EMAIL,))
    admin = cursor.fetchone()

    if not admin:
        cursor.execute(
            "INSERT INTO users (email, name) VALUES (?, ?)", (ADMIN_EMAIL, "Admin")
        )
        admin_id = cursor.lastrowid
        print(f"✅ Default admin user created: {ADMIN_EMAIL} (id={admin_id})")
    else:
        admin_id = admin[0]
        print(f"ℹ️  Admin user already exists: {ADMIN_EMAIL} (id={admin_id})")

    # Backfill sessions with NULL created_by
    cursor.execute(
        "UPDATE interview_sessions SET created_by = ? WHERE created_by IS NULL",
        (admin_id,),
    )
    backfilled = cursor.rowcount
    if backfilled > 0:
        print(f"✅ Backfilled {backfilled} existing sessions to admin user.")
    else:
        print("ℹ️  No orphan sessions to backfill.")

    conn.commit()
    conn.close()
    print("\n🎉 Auth migration complete!")


if __name__ == "__main__":
    migrate()
