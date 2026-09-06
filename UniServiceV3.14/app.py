from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_connection, init_db

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-antes-de-publicar"


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

        if not username or not email or not password:
            flash("Completa los campos obligatorios.")
            return render_template("register.html")

        conn = get_connection()
        exists = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()
        if exists:
            conn.close()
            flash("Ese usuario o correo ya esta registrado.")
            return render_template("register.html")

        conn.execute(
            """
            INSERT INTO users (username, email, password_hash, university, career)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, email, generate_password_hash(password), university, career),
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
    conn = get_connection()
    posts = conn.execute(
        """
        SELECT p.*, u.username,
               (SELECT COALESCE(SUM(value), 0) FROM forum_votes WHERE post_id = p.id) AS score,
               (SELECT COUNT(*) FROM forum_comments WHERE post_id = p.id) AS comment_count
        FROM forum_posts p
        JOIN users u ON u.id = p.user_id
        ORDER BY p.created_at DESC
        """
    ).fetchall()
    conn.close()
    return render_template("forum.html", posts=posts)


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
        conn.execute(
            "INSERT INTO forum_posts (user_id, title, content) VALUES (?, ?, ?)",
            (session["user_id"], title, content),
        )
        conn.commit()
        conn.close()
        flash("Pregunta publicada en el foro.")
        return redirect(url_for("forum"))

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
    return render_template("forum_post.html", post=post, comments=comments)


@app.route("/foro/<int:post_id>/votar/<int:value>")
@login_required
def vote_forum_post(post_id, value):
    if value not in (1, -1):
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
    conn = get_connection()
    my_services = conn.execute(
        "SELECT * FROM services WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],),
    ).fetchall()
    my_posts = conn.execute(
        "SELECT * FROM forum_posts WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return render_template("profile.html", my_services=my_services, my_posts=my_posts)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
