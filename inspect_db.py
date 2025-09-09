import sqlite3
import sys
from textwrap import shorten

DB = "feed.db"

def fetch_all(table: str):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table}")
        rows = cur.fetchall()
        return rows
    except sqlite3.Error as e:
        print(f"❌ Error: {e}")
        return []
    finally:
        conn.close()

def pretty_print(rows):
    if not rows:
        print("⚠️ No rows found.")
        return

    # Column names
    headers = rows[0].keys()
    col_widths = {h: max(len(h), 20) for h in headers}

    # Print header
    header_row = " | ".join(h.ljust(col_widths[h]) for h in headers)
    print(header_row)
    print("-" * len(header_row))

    # Print rows (truncate long text like captions)
    for row in rows:
        print(" | ".join(
            shorten(str(row[h]), width=col_widths[h]-2, placeholder="..").ljust(col_widths[h])
            for h in headers
        ))

if __name__ == "__main__":
    table = sys.argv[1] if len(sys.argv) > 1 else "posts"
    print(f"📂 Inspecting table: {table}\n")
    rows = fetch_all(table)
    pretty_print(rows)

## Inspect posts
# python inspect_db.py posts

# Inspect users
##python inspect_db.py users

# Inspect stories
#python inspect_db.py stories
