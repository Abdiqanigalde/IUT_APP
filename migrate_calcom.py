"""
migrate_calcom.py
─────────────────
Run ONCE after deploying the Cal.com booking update.

Adds the following columns to the `appointment` table:
  - duration       INTEGER  (default 15 — minutes)
  - notes          TEXT
  - meeting_type   VARCHAR(50) (default 'in_person')
  - timezone       VARCHAR(50) (default 'Asia/Dhaka')
  - location       VARCHAR(255)

Creates the new `appointment_history` table.

Usage:
  python migrate_calcom.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app import app, db
from sqlalchemy import text, inspect as sa_inspect

def run():
    with app.app_context():
        insp = sa_inspect(db.engine)
        is_pg = 'postgresql' in str(db.engine.url)

        # ── appointment table columns ──────────────────────────────────────────
        existing_cols = {c['name'] for c in insp.get_columns('appointment')}

        new_cols = [
            ("duration",     "INTEGER DEFAULT 15"),
            ("notes",        "TEXT"),
            ("meeting_type", "VARCHAR(50) DEFAULT 'in_person'"),
            ("timezone",     "VARCHAR(50) DEFAULT 'Asia/Dhaka'"),
            ("location",     "VARCHAR(255)"),
        ]

        with db.engine.connect() as conn:
            for col_name, col_def in new_cols:
                if col_name not in existing_cols:
                    print(f"  Adding column: appointment.{col_name}")
                    conn.execute(text(f"ALTER TABLE appointment ADD COLUMN {col_name} {col_def}"))
                else:
                    print(f"  Skipping (exists): appointment.{col_name}")
            conn.commit()

        # ── appointment_history table ──────────────────────────────────────────
        if 'appointment_history' not in insp.get_table_names():
            print("  Creating table: appointment_history")
            db.create_all()   # safe — only creates missing tables
        else:
            print("  Skipping (exists): appointment_history")

        print("\n✅  Migration complete.")

if __name__ == '__main__':
    run()
