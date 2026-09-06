import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "uniservice.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    _migrate(conn)
    conn.close()


def _migrate(conn):
    """Agrega columnas nuevas a bases de datos creadas con un schema anterior."""
    existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "role" not in existing_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'solicitante'"
        )
    if "avatar_filename" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_filename TEXT")
    if "banner_filename" not in existing_columns:
        conn.execute("ALTER TABLE users ADD COLUMN banner_filename TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forum_post_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (post_id) REFERENCES forum_posts(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()


if __name__ == "__main__":
    init_db()
    print("Base de datos creada en:", DB_PATH)
