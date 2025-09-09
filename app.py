import os, uuid, datetime, sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
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
        username=session.get("username")
    )


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
            session["username"] = row["username"]
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
    posts = conn.execute("""
        SELECT p.id, p.caption, p.media_url, p.media_type, p.created_at, u.username
        FROM posts p
        JOIN users u ON u.id = p.user_id
        ORDER BY p.created_at DESC
    """).fetchall()

    stories = conn.execute("""
        SELECT s.id, s.media_url, s.media_type, s.created_at, s.expires_at, u.username
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
        username=session.get("username")
    )


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


# -------- Profile --------
@app.route("/u/<username>")
def profile(username):
    conn = get_db()
    u = conn.execute(
        "SELECT id, username, avatar_url, bio, created_at FROM users WHERE username=?",
        (username,)
    ).fetchone()

    posts = []
    if u:
        posts = conn.execute("""
            SELECT id, caption, media_url, media_type, created_at
            FROM posts WHERE user_id=? ORDER BY created_at DESC
        """, (u["id"],)).fetchall()
    conn.close()

    if not u:
        return "User not found", 404

    return render_template("feed.html", posts=posts, stories=[], username=username)

# ---------- Run ----------
if __name__ == "__main__":
    if not os.path.exists(DB):
        import init_db
        init_db.init_db()
    app.run(debug=True)
