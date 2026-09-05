import os
import uuid
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from db import get_connection, init_db

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-antes-de-publicar"

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB por imagen
MAX_FORUM_IMAGES = 5
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024  # cubre hasta 5 imagenes + avatar/banner

AVATAR_FOLDER = os.path.join(app.root_path, "static", "uploads", "avatars")
BANNER_FOLDER = os.path.join(app.root_path, "static", "uploads", "banners")
FORUM_IMAGES_FOLDER = os.path.join(app.root_path, "static", "uploads", "forum")
os.makedirs(AVATAR_FOLDER, exist_ok=True)
os.makedirs(BANNER_FOLDER, exist_ok=True)
os.makedirs(FORUM_IMAGES_FOLDER, exist_ok=True)


# ---------- helpers ----------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Debes iniciar sesion para continuar.")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    if "user_id" not in session:
        return None
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return user


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(file_storage, folder, old_filename=None):
    """Guarda una imagen subida con un nombre unico y borra la anterior si existia.
    Devuelve el nuevo nombre de archivo, o None si no se subio nada valido."""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_image(file_storage.filename):
        flash("Formato de imagen no permitido. Usa PNG, JPG, GIF o WEBP.")
        return None

    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    new_filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(folder, new_filename))

    if old_filename:
        old_path = os.path.join(folder, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    return new_filename


@app.errorhandler(413)
def file_too_large(e):
    flash("Los archivos subidos superan el limite permitido (5 MB por imagen, 5 imagenes maximo).")
    return redirect(request.referrer or url_for("index"))


def save_forum_images(post_id, files):
    """Guarda hasta MAX_FORUM_IMAGES imagenes validas para una publicacion del foro."""
    conn = get_connection()
    saved_count = 0
    skipped_invalid = 0
    skipped_too_many = 0

    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue

        if saved_count >= MAX_FORUM_IMAGES:
            skipped_too_many += 1
            continue

        if not allowed_image(file_storage.filename):
            skipped_invalid += 1
            continue

        ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
        new_filename = f"{uuid.uuid4().hex}.{ext}"
        path = os.path.join(FORUM_IMAGES_FOLDER, new_filename)
        file_storage.save(path)

        if os.path.getsize(path) > MAX_IMAGE_SIZE:
            os.remove(path)
            skipped_invalid += 1
            continue

        conn.execute(
            "INSERT INTO forum_post_images (post_id, filename, position) VALUES (?, ?, ?)",
            (post_id, new_filename, saved_count),
        )
        saved_count += 1

    conn.commit()
    conn.close()

    if skipped_invalid:
        flash("Algunas imagenes no se subieron: formato no permitido o pesan mas de 5 MB.")
    if skipped_too_many:
        flash(f"Solo se permiten {MAX_FORUM_IMAGES} imagenes por publicacion; el resto se ignoro.")


@app.context_processor
def inject_user():
    return {"logged_user": current_user()}


# ---------- paginas generales ----------

@app.route("/")
def index():
    conn = get_connection()
    services = conn.execute(
        """
        SELECT s.*, u.username, c.name AS category_name,
               (SELECT ROUND(AVG(rating), 1) FROM reviews WHERE service_id = s.id) AS avg_rating,
               (SELECT COUNT(*) FROM reviews WHERE service_id = s.id) AS review_count
        FROM services s
        JOIN users u ON u.id = s.user_id
        JOIN categories c ON c.id = s.category_id
        WHERE s.is_active = 1
        ORDER BY s.created_at DESC
        LIMIT 12
        """
    ).fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()
    return render_template("index.html", services=services, categories=categories)


# ---------- autenticacion ----------

@app.route("/registro", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        university = request.form.get("university", "").strip()
        career = request.form.get("career", "").strip()
        role = request.form.get("role", "solicitante").strip()

        if role not in ("solicitante", "proveedor"):
            role = "solicitante"

        if not username or not email or not password:
            flash("Completa los campos obligatorios.")
            return render_template("register.html", role=role)

        conn = get_connection()
        exists = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()
        if exists:
            conn.close()
            flash("Ese usuario o correo ya esta registrado.")
            return render_template("register.html", role=role)

        conn.execute(
            """
            INSERT INTO users (username, email, password_hash, university, career, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, email, generate_password_hash(password), university, career, role),
        )
        conn.commit()
        conn.close()
        flash("Cuenta creada. Ya puedes iniciar sesion.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Correo o contrasena incorrectos.")
            return render_template("login.html")

        session["user_id"] = user["id"]
        flash(f"Bienvenido, {user['username']}.")
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- servicios ----------

@app.route("/servicios")
def services():
    category_slug = request.args.get("categoria", "")
    query = request.args.get("q", "").strip()

    sql = """
        SELECT s.*, u.username, c.name AS category_name, c.slug AS category_slug,
               (SELECT ROUND(AVG(rating), 1) FROM reviews WHERE service_id = s.id) AS avg_rating,
               (SELECT COUNT(*) FROM reviews WHERE service_id = s.id) AS review_count
        FROM services s
        JOIN users u ON u.id = s.user_id
        JOIN categories c ON c.id = s.category_id
        WHERE s.is_active = 1
    """
    params = []

    if category_slug:
        sql += " AND c.slug = ?"
        params.append(category_slug)

    if query:
        sql += " AND (s.title LIKE ? OR s.description LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like])

    sql += " ORDER BY s.created_at DESC"

    conn = get_connection()
    services_list = conn.execute(sql, params).fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()

    return render_template(
        "services.html",
        services=services_list,
        categories=categories,
        selected_category=category_slug,
        query=query,
    )


@app.route("/servicios/nuevo", methods=["GET", "POST"])
@login_required
def new_service():
    user = current_user()
    if user["role"] != "proveedor":
        flash("Solo las cuentas de proveedor pueden publicar servicios.")
        return redirect(url_for("services"))

    conn = get_connection()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form["description"].strip()
        price = request.form.get("price", "").strip()
        category_id = request.form["category_id"]
        delivery_mode = request.form.get("delivery_mode", "presencial")

        if not title or not description:
            conn.close()
            flash("El titulo y la descripcion son obligatorios.")
            return render_template("new_service.html", categories=categories)

        conn.execute(
            """
            INSERT INTO services (user_id, category_id, title, description, price, delivery_mode)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                category_id,
                title,
                description,
                float(price) if price else None,
                delivery_mode,
            ),
        )
        conn.commit()
        conn.close()
        flash("Servicio publicado.")
        return redirect(url_for("services"))

    conn.close()
    return render_template("new_service.html", categories=categories)


@app.route("/servicios/<int:service_id>", methods=["GET", "POST"])
def service_detail(service_id):
    conn = get_connection()

    if request.method == "POST":
        if "user_id" not in session:
            conn.close()
            flash("Debes iniciar sesion para dejar una resena.")
            return redirect(url_for("login"))

        rating = int(request.form["rating"])
        comment = request.form.get("comment", "").strip()

        conn.execute(
            """
            INSERT INTO reviews (service_id, user_id, rating, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (service_id, user_id)
            DO UPDATE SET rating = excluded.rating, comment = excluded.comment
            """,
            (service_id, session["user_id"], rating, comment),
        )
        conn.commit()
        flash("Gracias por tu retroalimentacion.")

    service = conn.execute(
        """
        SELECT s.*, u.username, u.university, u.career, c.name AS category_name
        FROM services s
        JOIN users u ON u.id = s.user_id
        JOIN categories c ON c.id = s.category_id
        WHERE s.id = ?
        """,
        (service_id,),
    ).fetchone()

    if service is None:
        conn.close()
        abort(404)

    reviews = conn.execute(
        """
        SELECT r.*, u.username
        FROM reviews r
        JOIN users u ON u.id = r.user_id
        WHERE r.service_id = ?
        ORDER BY r.created_at DESC
        """,
        (service_id,),
    ).fetchall()

    avg_rating = conn.execute(
        "SELECT ROUND(AVG(rating), 1) AS avg FROM reviews WHERE service_id = ?",
        (service_id,),
    ).fetchone()["avg"]

    conn.close()
    return render_template(
        "service_detail.html", service=service, reviews=reviews, avg_rating=avg_rating
    )


# ---------- foro ----------

@app.route("/foro")
def forum():
    query = request.args.get("q", "").strip()
    sort = request.args.get("orden", "recientes")
    if sort not in ("recientes", "top"):
        sort = "recientes"

    sql = """
        SELECT p.*, u.username,
               (SELECT COALESCE(SUM(value), 0) FROM forum_votes WHERE post_id = p.id) AS score,
               (SELECT COUNT(*) FROM forum_comments WHERE post_id = p.id) AS comment_count,
               (SELECT filename FROM forum_post_images WHERE post_id = p.id ORDER BY position LIMIT 1) AS thumbnail
        FROM forum_posts p
        JOIN users u ON u.id = p.user_id
    """
    params = []

    if query:
        sql += " WHERE (p.title LIKE ? OR p.content LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like])

    sql += " ORDER BY score DESC" if sort == "top" else " ORDER BY p.created_at DESC"

    conn = get_connection()
    posts = conn.execute(sql, params).fetchall()
    conn.close()
    return render_template("forum.html", posts=posts, query=query, sort=sort)


@app.route("/foro/nuevo", methods=["GET", "POST"])
@login_required
def new_forum_post():
    if request.method == "POST":
        title = request.form["title"].strip()
        content = request.form["content"].strip()

        if not title or not content:
            flash("El titulo y el contenido son obligatorios.")
            return render_template("new_forum_post.html")

        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO forum_posts (user_id, title, content) VALUES (?, ?, ?)",
            (session["user_id"], title, content),
        )
        post_id = cursor.lastrowid
        conn.commit()
        conn.close()

        images = request.files.getlist("images")
        if images:
            save_forum_images(post_id, images)

        flash("Pregunta publicada en el foro.")
        return redirect(url_for("forum_post_detail", post_id=post_id))

    return render_template("new_forum_post.html")


@app.route("/foro/<int:post_id>", methods=["GET", "POST"])
def forum_post_detail(post_id):
    conn = get_connection()

    if request.method == "POST":
        if "user_id" not in session:
            conn.close()
            flash("Debes iniciar sesion para comentar.")
            return redirect(url_for("login"))

        content = request.form["content"].strip()
        if content:
            conn.execute(
                "INSERT INTO forum_comments (post_id, user_id, content) VALUES (?, ?, ?)",
                (post_id, session["user_id"], content),
            )
            conn.commit()

    post = conn.execute(
        """
        SELECT p.*, u.username,
               (SELECT COALESCE(SUM(value), 0) FROM forum_votes WHERE post_id = p.id) AS score
        FROM forum_posts p
        JOIN users u ON u.id = p.user_id
        WHERE p.id = ?
        """,
        (post_id,),
    ).fetchone()

    if post is None:
        conn.close()
        abort(404)

    images = conn.execute(
        "SELECT filename FROM forum_post_images WHERE post_id = ? ORDER BY position",
        (post_id,),
    ).fetchall()

    comments = conn.execute(
        """
        SELECT fc.*, u.username
        FROM forum_comments fc
        JOIN users u ON u.id = fc.user_id
        WHERE fc.post_id = ?
        ORDER BY fc.created_at ASC
        """,
        (post_id,),
    ).fetchall()

    conn.close()
    return render_template("forum_post.html", post=post, comments=comments, images=images)


@app.route("/foro/<int:post_id>/votar/<direction>")
@login_required
def vote_forum_post(post_id, direction):
    if direction == "up":
        value = 1
    elif direction == "down":
        value = -1
    else:
        abort(400)

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO forum_votes (post_id, user_id, value)
        VALUES (?, ?, ?)
        ON CONFLICT (post_id, user_id) DO UPDATE SET value = excluded.value
        """,
        (post_id, session["user_id"], value),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("forum_post_detail", post_id=post_id))


# ---------- perfil ----------

@app.route("/perfil")
@login_required
def profile():
    return redirect(url_for("user_profile", username=current_user()["username"]))


@app.route("/usuario/<username>")
def user_profile(username):
    conn = get_connection()
    profile_user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()

    if profile_user is None:
        conn.close()
        abort(404)

    my_services = conn.execute(
        "SELECT * FROM services WHERE user_id = ? ORDER BY created_at DESC",
        (profile_user["id"],),
    ).fetchall()
    my_posts = conn.execute(
        "SELECT * FROM forum_posts WHERE user_id = ? ORDER BY created_at DESC",
        (profile_user["id"],),
    ).fetchall()
    conn.close()

    is_own = "user_id" in session and session["user_id"] == profile_user["id"]

    return render_template(
        "profile.html",
        profile_user=profile_user,
        my_services=my_services,
        my_posts=my_posts,
        is_own=is_own,
    )


@app.route("/perfil/editar", methods=["GET", "POST"])
@login_required
def edit_profile():
    user = current_user()

    if request.method == "POST":
        bio = request.form.get("bio", "").strip()[:280]
        university = request.form.get("university", "").strip()
        career = request.form.get("career", "").strip()

        avatar_filename = user["avatar_filename"]
        new_avatar = save_uploaded_image(
            request.files.get("avatar"), AVATAR_FOLDER, old_filename=avatar_filename
        )
        if new_avatar:
            avatar_filename = new_avatar

        banner_filename = user["banner_filename"]
        new_banner = save_uploaded_image(
            request.files.get("banner"), BANNER_FOLDER, old_filename=banner_filename
        )
        if new_banner:
            banner_filename = new_banner

        conn = get_connection()
        conn.execute(
            """
            UPDATE users
            SET bio = ?, university = ?, career = ?, avatar_filename = ?, banner_filename = ?
            WHERE id = ?
            """,
            (bio, university, career, avatar_filename, banner_filename, user["id"]),
        )
        conn.commit()
        conn.close()
        flash("Perfil actualizado.")
        return redirect(url_for("user_profile", username=user["username"]))

    return render_template("edit_profile.html", user=user)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
