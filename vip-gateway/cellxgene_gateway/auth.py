import functools
import secrets

from flask import (
    Blueprint,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from cellxgene_gateway import models

auth_bp = Blueprint("auth", __name__, template_folder="templates")


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            return redirect(url_for("auth.login_page"))
        if not session.get("is_admin"):
            return jsonify({"ok": False, "error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400
    user = models.authenticate(username, password)
    if not user:
        return jsonify({"ok": False, "error": "Invalid username or password"}), 401
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["is_admin"] = bool(user["is_admin"])
    session.permanent = True
    return jsonify({"ok": True, "username": user["username"], "is_admin": bool(user["is_admin"])})


@auth_bp.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@auth_bp.route("/api/me", methods=["GET"])
def api_me():
    if "user_id" not in session:
        return jsonify({"ok": False, "authenticated": False}), 401
    return jsonify({
        "ok": True,
        "authenticated": True,
        "username": session["username"],
        "is_admin": session.get("is_admin", False),
    })
