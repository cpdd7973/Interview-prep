import sqlite3
from config import settings

db_path = settings.database_url.replace("sqlite:///", "")

print(f"Migrating database at: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    columns_to_add = [
        ("skill_plan", "JSON"),
        ("topics_covered", "JSON"),
        ("current_phase", "VARCHAR(20)"),
        ("interview_started_at", "DATETIME"),
    ]

    # Get existing columns
    cur.execute("PRAGMA table_info(interview_sessions)")
    existing_columns = [col[1] for col in cur.fetchall()]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            print(f"Adding column: {col_name}")
            cur.execute(
                f"ALTER TABLE interview_sessions ADD COLUMN {col_name} {col_type}"
            )
        else:
            print(f"Column {col_name} already exists.")

    conn.commit()

    # Backfill: for sessions already in flight before this migration,
    # approximate interview_started_at from activated_at rather than
    # leaving it NULL (which would reset the 30-minute timer to "now"
    # on their next WebSocket reconnect).
    cur.execute(
        """
        UPDATE interview_sessions
        SET interview_started_at = activated_at
        WHERE interview_started_at IS NULL AND activated_at IS NOT NULL
        """
    )
    print(f"Backfilled interview_started_at for {cur.rowcount} session(s).")
    conn.commit()

    print("Migration successful.")
except Exception as e:
    print(f"Migration error: {e}")
finally:
    if "conn" in locals():
        conn.close()
