import sqlite3
from config import settings

db_path = settings.database_url.replace("sqlite:///", "")

print(f"Migrating database at: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    columns_to_add = [
        ("criteria_reasoning", "JSON"),
    ]

    cur.execute("PRAGMA table_info(evaluations)")
    existing_columns = [col[1] for col in cur.fetchall()]

    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            print(f"Adding column: {col_name}")
            cur.execute(f"ALTER TABLE evaluations ADD COLUMN {col_name} {col_type}")
        else:
            print(f"Column {col_name} already exists.")

    conn.commit()
    print("Migration successful.")
except Exception as e:
    print(f"Migration error: {e}")
finally:
    if "conn" in locals():
        conn.close()
