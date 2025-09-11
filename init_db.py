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

        # ---------- Likes ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_likes_post_id ON likes(post_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_likes_user_id ON likes(user_id);")

        # ---------- Comments ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id);")

        # ---------- Messages ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            content TEXT,
            media_url TEXT,
            media_type TEXT CHECK(media_type IN ('image','video','file')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_receiver_id ON messages(receiver_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);")

        conn.commit()
        print(f"✅ Database ready: {DB}")

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
