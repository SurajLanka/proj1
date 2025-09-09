import sqlite3

DB = "feed.db"

def init_db():
    conn = sqlite3.connect(DB)
    try:
        # Enforce foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

        # ---------- Users ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            avatar_url TEXT,
            bio TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Index for fast login lookups
        cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")

        # ---------- Posts ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            caption TEXT,
            media_url TEXT,
            media_type TEXT CHECK(media_type IN ('image','video')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC);")

        # ---------- Stories ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            media_url TEXT,
            media_type TEXT CHECK(media_type IN ('image','video')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_stories_user_id ON stories(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stories_expires_at ON stories(expires_at);")

        conn.commit()
        print(f"✅ Database ready: {DB}")

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
