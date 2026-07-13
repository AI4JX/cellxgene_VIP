import os
import sqlite3
import threading
import logging
from werkzeug.security import generate_password_hash, check_password_hash

_local = threading.local()


def _get_db(db_path):
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(db_path, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def get_db():
    import cellxgene_gateway.env as env
    return _get_db(env.db_path)


def init_db(db_path=None):
    if db_path is None:
        import cellxgene_gateway.env as env
        db_path = env.db_path
    if not db_path or db_path == ":memory:":
        raise ValueError(
            "GATEWAY_DB_PATH is empty or :memory:. "
            "Set GATEWAY_DB_PATH to a persistent file path to avoid data loss on restart."
        )
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _get_db(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS dataset_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            folder_path TEXT NOT NULL,
            UNIQUE(user_id, folder_path)
        );
    """)
    conn.commit()


def seed_admin(username, password):
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return
    db.execute(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
        (username, generate_password_hash(password)),
    )
    db.commit()


def authenticate(username, password):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def get_user(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_user_by_username(username):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def list_users():
    db = get_db()
    rows = db.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def create_user(username, password, is_admin=False):
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), 1 if is_admin else 0),
        )
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def delete_user(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


def update_password(user_id, password):
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )
    db.commit()


def get_user_permissions(user_id):
    db = get_db()
    rows = db.execute(
        "SELECT folder_path FROM dataset_permissions WHERE user_id = ? ORDER BY folder_path",
        (user_id,),
    ).fetchall()
    return [r["folder_path"] for r in rows]


def set_user_permissions(user_id, folder_paths):
    db = get_db()
    db.execute("DELETE FROM dataset_permissions WHERE user_id = ?", (user_id,))
    for fp in folder_paths:
        db.execute(
            "INSERT INTO dataset_permissions (user_id, folder_path) VALUES (?, ?)",
            (user_id, fp),
        )
    db.commit()


def is_dataset_visible(user_id, subfolder, all_users):
    """Check if a dataset is visible to a user.
    If the user has no permission records, all datasets are visible.
    """
    if all_users:
        return True
    db = get_db()
    rows = db.execute(
        "SELECT folder_path FROM dataset_permissions WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    if not rows:
        return True
    allowed = [r["folder_path"] for r in rows]
    return subfolder in allowed


def checkpoint_db():
    """Force WAL checkpoint to flush pending writes to the main db file.

    Call this on graceful shutdown to minimize the risk of uncommitted WAL
    data being lost when the container is stopped.
    """
    try:
        db = get_db()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        logging.getLogger("cellxgene_gateway").warning(
            "WAL checkpoint failed", exc_info=True
        )
