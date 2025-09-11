import os, uuid, datetime, sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------- Optional: Cloudinary ----------
# from dotenv import load_dotenv
# load_dotenv()
# import cloudinary
# import cloudinary.uploader

DB = "feed.db"
ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "avi", "mkv"}

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET", "change-me")  # change this in production!

# ---------- Cloudinary config (fallback to local if not set) ----------
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
USE_CLOUDINARY = False
try:
    if CLOUDINARY_URL:
        cloudinary.config(cloudinary_url=CLOUDINARY_URL, secure=True)
        USE_CLOUDINARY = True
    elif os.getenv("CLOUDINARY_CLOUD_NAME"):
        cloudinary.config(
            cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
            api_key=os.getenv("CLOUDINARY_API_KEY"),
            api_secret=os.getenv("CLOUDINARY_API_SECRET"),
            secure=True,
        )
        USE_CLOUDINARY = True
except Exception:
    USE_CLOUDINARY = False

# ---------- DB Helpers ----------
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS

def detect_media_type(mimetype: str) -> str:
    return "video" if mimetype and mimetype.startswith("video/") else "image"

def upload_media(file_storage):
    """
    Returns (media_url, media_type).
    Uses Cloudinary if configured, otherwise saves locally to static/uploads/.
    """
    if not file_storage or file_storage.filename == "":
        return None, None
    if not allowed_file(file_storage.filename):
        raise ValueError("File type not allowed")

    media_type = detect_media_type(file_storage.mimetype)

    if USE_CLOUDINARY:
        up = cloudinary.uploader.upload(
            file_storage,
            folder="instasnap",
            resource_type="auto"  # auto-detect image or video
        )
        return up["secure_url"], media_type
    else:
        os.makedirs(os.path.join("static", "uploads"), exist_ok=True)
        ext = file_storage.filename.rsplit(".", 1)[1].lower()
        fname = secure_filename(f"{uuid.uuid4().hex}.{ext}")
        path = os.path.join("static", "uploads", fname)
        file_storage.save(path)
        return f"/static/uploads/{fname}", media_type

# ---------- Routes ----------
@app.route("/")
def home():
    return render_template(
        "home.html",
        user_id=session.get("user_id"),
        username=session.get("username") or "Anonymous"
    )

@app.route("/dms")
@login_required
def dms():
    conn = get_db()
    user_id = session["user_id"]
    # Get all distinct users who you have messages with

    conversations = conn.execute("""
        SELECT DISTINCT u.id, u.username
        FROM users u
        JOIN messages m ON (u.id = m.sender_id OR u.id = m.receiver_id)
        WHERE (m.sender_id = ? OR m.receiver_id = ?) AND u.id != ?
        """, (user_id, user_id, user_id)).fetchall()

    conn.close()
    return render_template("dms.html", conversations=conversations, username=session.get("username"))

# -------- Auth --------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password required.")
            return redirect(url_for("signup"))

        pw_hash = generate_password_hash(password)
        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, pw_hash),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("Username already taken.")
            return redirect(url_for("signup"))
        finally:
            conn.close()

        flash("Signup successful. Please login.")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if row and check_password_hash(row["password_hash"], password):
            session["user_id"] = row["id"]
            session["username"] = row["username"] or "Anonymous"
            return redirect(url_for("feed"))

        flash("Invalid credentials.")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("home"))

# -------- Feed & Posts --------
@app.route("/feed", methods=["GET", "POST"])
@login_required
def feed():
    if request.method == "POST":
        caption = request.form.get("caption", "").strip()
        file = request.files.get("media")
        media_url, media_type = (None, None)

        if file and file.filename:
            try:
                media_url, media_type = upload_media(file)
            except ValueError as e:
                flash(str(e))
                return redirect(url_for("feed"))

        conn = get_db()
        conn.execute(
            "INSERT INTO posts (user_id, caption, media_url, media_type) VALUES (?,?,?,?)",
            (session["user_id"], caption, media_url, media_type),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("feed"))

    conn = get_db()
    rows = conn.execute("""
    SELECT p.id, p.user_id, p.caption, p.media_url, p.media_type, p.created_at, 
           COALESCE(u.username, 'Anonymous') as username,
           (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as like_count,
           (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comment_count,
           EXISTS(SELECT 1 FROM likes WHERE post_id = p.id AND user_id = ?) as liked_by_me
    FROM posts p
    JOIN users u ON u.id = p.user_id
    ORDER BY p.created_at DESC
""", (session["user_id"],)).fetchall()

    # convert rows to mutable dicts and attach the latest 3 comments
    posts = []
    for r in rows:
        post = dict(r)
        # fetch latest 3 comments (oldest-first within that slice)
        comment_rows = conn.execute("""
            SELECT c.id, c.content, c.created_at, COALESCE(u.username, 'Anonymous') as username
            FROM comments c
            JOIN users u ON u.id = c.user_id
            WHERE c.post_id = ?
            ORDER BY c.created_at ASC
            LIMIT 3
        """, (post["id"],)).fetchall()
        post["comments"] = [dict(c) for c in comment_rows]
        posts.append(post)

    stories = conn.execute("""
        SELECT s.id, s.media_url, s.media_type, s.created_at, s.expires_at, 
               COALESCE(u.username, 'Anonymous') as username
        FROM stories s
        JOIN users u ON u.id = s.user_id
        WHERE s.expires_at > CURRENT_TIMESTAMP
        ORDER BY s.created_at DESC
    """).fetchall()
    conn.close()
    return render_template(
        "feed.html",
        posts=posts,
        stories=stories,
        username=session.get("username") or "Anonymous")

# delete
@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    conn = get_db()
    cur = conn.cursor()
    
    # Check if post exists
    post = cur.execute("SELECT user_id, media_url FROM posts WHERE id=?", (post_id,)).fetchone()
    if not post:
        conn.close()
        flash("Post not found.")
        return redirect(url_for("feed"))

    # Check permission (only owner can delete)
    if post["user_id"] != session["user_id"]:
        conn.close()
        flash("You can't delete this post.")
        return redirect(url_for("feed"))

    # Delete file if stored locally
    if post["media_url"] and not USE_CLOUDINARY:
        media_path = post["media_url"].lstrip("/")
        if os.path.exists(media_path):
            os.remove(media_path)

    # Delete likes, comments, and post
    cur.execute("DELETE FROM likes WHERE post_id=?", (post_id,))
    cur.execute("DELETE FROM comments WHERE post_id=?", (post_id,))
    cur.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.commit()
    conn.close()

    flash("Post deleted successfully.")
    return redirect(url_for("feed"))

# -------- Likes --------
@app.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def toggle_like(post_id):
    conn = get_db()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT id FROM likes WHERE post_id=? AND user_id=?", 
        (post_id, session["user_id"])
    ).fetchone()

    if existing:
        cur.execute("DELETE FROM likes WHERE id=?", (existing["id"],))
        status = "unliked"
    else:
        cur.execute(
            "INSERT INTO likes (post_id, user_id, created_at) VALUES (?,?,CURRENT_TIMESTAMP)",
            (post_id, session["user_id"])
        )
        status = "liked"

    conn.commit()
    # fetch updated like count
    like_count = cur.execute("SELECT COUNT(*) FROM likes WHERE post_id=?", (post_id,)).fetchone()[0]
    conn.close()
    return jsonify({"status": status, "like_count": like_count})

# -------- Comments --------
@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def add_comment(post_id):
    content = request.form.get("content", "").strip()
    if not content:
        return jsonify({"error": "Empty comment"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO comments (post_id, user_id, content, created_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
        (post_id, session["user_id"], content)
    )
    conn.commit()
    new_id = cur.lastrowid
    # fetch newly inserted comment to return created_at too
    new_row = cur.execute("""
        SELECT c.id, c.content, c.created_at, COALESCE(u.username, 'Anonymous') as username
        FROM comments c
        JOIN users u ON u.id = c.user_id
        WHERE c.id = ?
    """, (new_id,)).fetchone()
    conn.close()
    if new_row:
        new_comment = dict(new_row)
    else:
        new_comment = {"id": new_id, "username": session.get("username"), "content": content}
    return jsonify({
        "status": "ok",
        "comment": new_comment
    })

@app.route("/post/<int:post_id>/comments")
@login_required
def get_comments(post_id):
    """Fetch comments for a post (supports limit & offset for 'more'/'less')"""
    limit = int(request.args.get("limit", 3))
    offset = int(request.args.get("offset", 0))

    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.content, c.created_at, u.username
        FROM comments c
        JOIN users u ON u.id = c.user_id
        WHERE c.post_id=?
        ORDER BY c.created_at ASC
        LIMIT ? OFFSET ?
    """, (post_id, limit, offset)).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM comments WHERE post_id=?", (post_id,)
    ).fetchone()[0]
    conn.close()

    comments = [dict(r) for r in rows]
    return jsonify({"comments": comments, "total": total})

# -------- Stories --------
@app.route("/stories", methods=["POST"])
@login_required
def add_story():
    file = request.files.get("story_media")
    if not file or not file.filename:
        flash("Select a file for your story.")
        return redirect(url_for("feed"))

    try:
        media_url, media_type = upload_media(file)
    except ValueError as e:
        flash(str(e))
        return redirect(url_for("feed"))

    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    conn.execute("""
        INSERT INTO stories (user_id, media_url, media_type, expires_at)
        VALUES (?,?,?,?)
    """, (session["user_id"], media_url, media_type, expires_at))
    conn.commit()
    conn.close()
    return redirect(url_for("feed"))

# -------- Direct Messaging --------
@app.route("/messages/<username>", methods=["GET", "POST"])
@login_required
def messages(username):
    conn = get_db()

    # find receiver
    receiver = conn.execute("SELECT id, username FROM users WHERE username=?", (username,)).fetchone()
    if not receiver:
        conn.close()
        return "User not found", 404

    # send message
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        file = request.files.get("media")

        media_url = None
        if file and file.filename:
            media_url, _ = upload_media(file)

        if content or media_url:
            conn.execute("""
                INSERT INTO messages (sender_id, receiver_id, content, media_url)
                VALUES (?, ?, ?, ?)
            """, (session["user_id"], receiver["id"], content, media_url))
            conn.commit()

        return redirect(url_for("messages", username=username))

    # fetch chat history (both ways)
    chat = conn.execute("""
        SELECT m.*, u.username as sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (m.sender_id=? AND m.receiver_id=?) OR (m.sender_id=? AND m.receiver_id=?)
        ORDER BY m.created_at ASC
    """, (session["user_id"], receiver["id"], receiver["id"], session["user_id"])).fetchall()

    conn.close()
    return render_template("messages.html", chat=chat, receiver=receiver, username=session.get("username"))

# -------- Profile --------
@app.route("/u/<username>")
def profile(username):
    conn = get_db()
    u = conn.execute(
        "SELECT id, username, avatar_url, bio, created_at FROM users WHERE username=?",
        (username,),
    ).fetchone()

    if not u:
        conn.close()
        return "User not found", 404

    posts = conn.execute("""
        SELECT p.id, p.user_id, p.caption, p.media_url, p.media_type, p.created_at,
               COALESCE(usr.username, 'Anonymous') as username,
               (SELECT COUNT(*) FROM likes WHERE post_id = p.id) as like_count,
               (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comment_count,
               EXISTS(SELECT 1 FROM likes WHERE post_id = p.id AND user_id = ?) as liked_by_me
        FROM posts p
        JOIN users usr ON usr.id = p.user_id
        WHERE p.user_id = ?
        ORDER BY p.created_at DESC
    """, (session.get("user_id"), u["id"])).fetchall()

    conn.close()
    # convert rows to dicts for template compatibility (if needed)
    posts = [dict(r) for r in posts]
    return render_template("feed.html", posts=posts, stories=[], username=username or "Anonymous")

# ---------- Run ----------
if __name__ == "__main__":
    if not os.path.exists(DB):
        import init_db
        init_db.init_db()
    app.run(debug=True)
