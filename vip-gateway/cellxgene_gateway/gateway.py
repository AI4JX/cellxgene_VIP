# Copyright 2019 Novartis Institutes for BioMedical Research Inc. Licensed
# under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0. Unless
# required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES
# OR CONDITIONS OF ANY KIND, either express or implied. See the License for
# the specific language governing permissions and limitations under the License.
import atexit
import datetime
import json
import logging
import os
import shutil
import urllib.parse
from datetime import timedelta
from threading import Lock, Thread

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix

from cellxgene_gateway import env, flask_util, models
from cellxgene_gateway.dir_util import annotations_suffix, vipconfig_path
from cellxgene_gateway.auth import auth_bp, login_required, admin_required
from cellxgene_gateway.backend_cache import BackendCache
from cellxgene_gateway.cache_entry import CacheEntryStatus
from cellxgene_gateway.cache_key import CacheKey
from cellxgene_gateway.cellxgene_exception import CellxgeneException
from cellxgene_gateway.extra_scripts import get_extra_scripts
from cellxgene_gateway.filecrawl import render_item_source
from cellxgene_gateway.process_exception import ProcessException
from cellxgene_gateway.prune_process_cache import PruneProcessCache
from cellxgene_gateway.util import current_time_stamp

app = Flask(__name__)
app.secret_key = env.secret_key or "dev-secret-change-me"
app.permanent_session_lifetime = timedelta(days=7)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.register_blueprint(auth_bp)

item_sources = []
default_item_source = None

# Guard for lazy initialization so tests can import this module without
# triggering environment-dependent side effects. initialize_data_sources()
# will set this to True when it has run.
data_sources_initialized = False
data_sources_init_lock = Lock()


def _force_https(app):
    def wrapper(environ, start_response):
        if env.external_protocol is not None:
            environ["wsgi.url_scheme"] = env.external_protocol
        return app(environ, start_response)

    return wrapper


def set_no_cache(resp):
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Cache-Control"] = "public, max-age=0"
    return resp


app.wsgi_app = _force_https(app.wsgi_app)
if (
    env.proxy_fix_for > 0
    or env.proxy_fix_proto > 0
    or env.proxy_fix_host > 0
    or env.proxy_fix_port > 0
    or env.proxy_fix_prefix > 0
):
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=env.proxy_fix_for,
        x_proto=env.proxy_fix_proto,
        x_host=env.proxy_fix_host,
        x_port=env.proxy_fix_port,
        x_prefix=env.proxy_fix_prefix,
    )


# WSGI middleware to ensure data sources are initialized before the first
# WSGI request is handled. This guarantees initialization works under
# Gunicorn/uWSGI (which import the module but don't call main()). The
# initialize_data_sources() function is idempotent-protected by
# data_sources_initialized and data_sources_init_lock.
def _init_on_first_wsgi_request(wsgi_app):
    def middleware(environ, start_response):
        global data_sources_initialized
        if not data_sources_initialized:
            with data_sources_init_lock:
                if not app.extensions.get("cellxgene_gateway", {}).get("launchtime"):
                    app.extensions.setdefault("cellxgene_gateway", {})[
                        "launchtime"
                    ] = current_time_stamp()

                if not data_sources_initialized:
                    initialize_data_sources()

                    env.validate()
                    if not item_sources or not len(item_sources):
                        raise Exception(
                            "No data sources specified for Cellxgene Gateway"
                        )

                    global default_item_source
                    if default_item_source is None:
                        default_item_source = item_sources[0]

                    models.init_db()
                    if env.admin_user and env.admin_password:
                        models.seed_admin(env.admin_user, env.admin_password)

                    data_sources_initialized = True
        return wsgi_app(environ, start_response)

    return middleware


# Wrap the WSGI app so Gunicorn/uWSGI will trigger initialization when the
# first request comes in. Tests that need initialization can call
# initialize_data_sources() directly.
app.wsgi_app = _init_on_first_wsgi_request(app.wsgi_app)

cache = BackendCache()


# Initialize data sources - this is defined later in the file but called here
# to ensure initialization happens when WSGI servers (Gunicorn) import the module
def initialize_data_sources():
    """Initialize data sources from environment variables.
    Called at module import time for WSGI server compatibility (Gunicorn).
    Uses a guard flag to prevent double initialization within a process."""
    global default_item_source

    logging.basicConfig(
        level=env.log_level,
        format="%(asctime)s:%(name)s:%(levelname)s:%(message)s",
    )
    logger = logging.getLogger(__name__)

    cellxgene_data = os.environ.get("CELLXGENE_DATA", None)
    cellxgene_bucket = os.environ.get("CELLXGENE_BUCKET", None)

    if cellxgene_bucket is not None:
        from cellxgene_gateway.items.s3.s3item_source import S3ItemSource

        s3_source = S3ItemSource(cellxgene_bucket, name="s3")
        item_sources.append(s3_source)
        default_item_source = s3_source
        logger.info("Initialized S3 data source")
        logger.debug(f"S3 bucket: {cellxgene_bucket}")
    if cellxgene_data is not None:
        from cellxgene_gateway.items.file.fileitem_source import FileItemSource

        file_source = FileItemSource(cellxgene_data, name="local")
        item_sources.append(file_source)
        default_item_source = file_source
        logger.info("Initialized local file data source")
        logger.debug(f"Data directory: {cellxgene_data}")
    if len(item_sources) == 0:
        raise Exception("Please specify CELLXGENE_DATA or CELLXGENE_BUCKET")
    flask_util.include_source_in_url = len(item_sources) > 1


@app.errorhandler(CellxgeneException)
def handle_invalid_usage(error):
    message = f"{error.http_status} Error : {error.message}"

    return (
        render_template(
            "cellxgene_error.html",
            extra_scripts=get_extra_scripts(),
            message=message,
        ),
        error.http_status,
    )


@app.errorhandler(ProcessException)
def handle_invalid_process(error):
    message = []

    message.append(error.message)
    message.append(f"{error.http_status} Error.")
    message.append(f"Stdout: {error.stdout}")
    message.append(f"Stderr: {error.stderr}")

    return (
        render_template(
            "process_error.html",
            extra_scripts=get_extra_scripts(),
            message=error.message,
            http_status=error.http_status,
            stdout=error.stdout,
            stderr=error.stderr,
            relaunch_url=error.key.relaunch_url(),
            annotation_file=error.key.annotation_descriptor,
        ),
        error.http_status,
    )


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "nibr.ico",
        mimetype="image/vnd.microsof.icon",
    )


@app.route("/")
def index():
    return redirect(url_for("filecrawl"))


@app.route("/filecrawl")
def filecrawl_redirect():
    return redirect(url_for("filecrawl"))


@app.route("/filecrawl.html")
@app.route("/filecrawl/<path:path>")
@login_required
def filecrawl(path=None):
    source_name = request.args.get("source")
    sources = (
        filter(
            lambda x: x.name == urllib.parse.unquote_plus(source_name),
            item_sources,
        )
        if source_name
        else item_sources
    )
    # loop all data sources --
    rendered_sources = [
        render_item_source(item_source, path) for item_source in sources
    ]  # will we need to make this async in the page???
    rendered_html = "\n".join(rendered_sources)

    resp = make_response(
        render_template(
            "filecrawl.html",
            extra_scripts=get_extra_scripts(),
            rendered_html=rendered_html,
            path=path,
            username=session.get("username", ""),
            is_admin=session.get("is_admin", False),
        )
    )
    set_no_cache(resp)
    return resp


entry_lock = Lock()


def matching_source(source_name):
    if source_name is None and default_item_source is not None:
        source_name = default_item_source.name
    matching = [i for i in item_sources if i.name == source_name]
    if len(matching) != 1:
        raise Exception(f"Could not find matching item source {source_name}")
    source = matching[0]
    return source


@app.route(
    "/source/<path:source_name>/view/<path:path>",
    methods=["GET", "PUT", "POST"],
)
@app.route("/view/<path:path>", methods=["GET", "PUT", "POST"])
@login_required
def do_view(path, source_name=None):
    path = urllib.parse.unquote(path)
    source = matching_source(source_name)
    match = cache.check_path(source, path)

    if match is None:
        lookup = source.lookup(path)
        if lookup is None:
            raise CellxgeneException(
                f"Could not find item for path {path} in source {source.name}",
                404,
            )
        key = CacheKey.for_lookup(source, lookup)
        print(
            f"view path={path}, source_name={source_name}, dataset={key.file_path}, annotation_file= {key.annotation_file_path}, key={key.descriptor}, source={key.source_name}"
        )
        with entry_lock:
            match = cache.check_entry(key)
            if match is None:
                uascripts = get_extra_scripts()
                match = cache.create_entry(key, uascripts)

    match.timestamp = current_time_stamp()

    if (
        match.status == CacheEntryStatus.loaded
        or match.status == CacheEntryStatus.loading
    ):
        if source.is_authorized(match.key.descriptor):
            return match.serve_content(path)
        else:
            raise CellxgeneException("User not authorized to access this data", 403)
    elif match.status == CacheEntryStatus.error:
        raise ProcessException.from_cache_entry(match)
    else:
        raise CellxgeneException(
            f"Unexpected cache entry status {match.status} for key {match.key.descriptor}",
            500,
        )


@app.route("/cache_status", methods=["GET"])
def do_GET_status():
    return render_template(
        "cache_status.html",
        entry_list=cache.entry_list,
        extra_scripts=get_extra_scripts(),
    )


@app.route("/cache_status.json", methods=["GET"])
def do_GET_status_json():
    def map_entry(entry):
        dataset = entry.key.h5ad_item.descriptor
        annotation_file = entry.key.annotation_descriptor
        return {
            "dataset": dataset,
            "annotation_file": annotation_file,
            "launchtime": entry.launchtime,
            "last_access": entry.timestamp,
            "status": entry.status.name,
        }

    return json.dumps(
        {
            "launchtime": app.extensions.get("cellxgene_gateway", {}).get("launchtime"),
            "entry_list": [map_entry(entry) for entry in cache.entry_list],
        }
    )


def get_cache_key(path):
    path = urllib.parse.unquote(path)
    if request.args.get("source_name"):
        source_name = request.args.get("source_name")
    elif default_item_source:
        source_name = default_item_source.name
    else:
        source_name = None
    source = matching_source(source_name)
    key = CacheKey.for_lookup(source, source.lookup(path))
    return key


@app.route("/relaunch/<path:path>", methods=["GET"])
def do_relaunch(path):
    key = get_cache_key(path)
    match = cache.check_entry(key)
    if not match is None:
        match.terminate()
    return redirect(
        key.view_url,
        code=302,
    )


@app.route("/terminate/<path:path>", methods=["GET"])
def do_terminate(path):
    key = get_cache_key(path)
    match = cache.check_entry(key)
    if not match is None:
        match.terminate()
    return redirect(url_for("do_GET_status"), code=302)


# ---------------------------------------------------------------------------
# API endpoints for the frontend
# ---------------------------------------------------------------------------

def _iter_datasets(item_source):
    """Yield (subfolder, FileItem) pairs from an ItemSource."""
    tree = item_source.list_items()
    def walk(node, prefix=""):
        for item in (node.items or []):
            yield prefix, item
        for branch in (node.branches or []):
            sub = branch.descriptor.lstrip("/")
            yield from walk(branch, sub)
    yield from walk(tree)


def _get_status_for(source_name, descriptor):
    """Check the cache for a running entry matching descriptor."""
    for entry in cache.entry_list:
        if entry.key.source_name == source_name and entry.key.h5ad_item.descriptor == descriptor:
            return entry.status.name, entry.port
    return "stopped", None


def _get_file_metadata(source, descriptor):
    """Return size and mtime for a dataset file if the source supports it."""
    full_path = getattr(source, "full_path", None)
    if full_path is None:
        return 0, ""
    try:
        fp = full_path(descriptor)
        st = os.stat(fp)
        return st.st_size, datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.timezone.utc).isoformat()
    except OSError:
        return 0, ""


def _get_annotations(item_source, item):
    """Return list of annotation names for a dataset."""
    if not env.enable_annotations:
        return []
    anns = item.annotations or []
    return [a.name + a.ext for a in anns]


@app.route("/api/datasets", methods=["GET"])
@login_required
def api_datasets():
    user_id = session.get("user_id")
    has_permissions = False
    if user_id:
        perms = models.get_user_permissions(user_id)
        has_permissions = bool(perms)
    result = []
    for source in item_sources:
        for subfolder, item in _iter_datasets(source):
            if has_permissions and subfolder not in perms:
                continue
            status, port = _get_status_for(source.name, item.descriptor)
            size, mtime = _get_file_metadata(source, item.descriptor)
            annotations = _get_annotations(source, item)
            result.append({
                "name": item.name,
                "descriptor": item.descriptor,
                "subfolder": subfolder,
                "source": source.name,
                "size": size,
                "mtime": mtime,
                "status": status,
                "port": port,
                "annotations": annotations,
                "annotation_subpath": source.get_annotations_subpath(item) if env.enable_annotations else None,
            })
    resp = jsonify(result)
    set_no_cache(resp)
    return resp


@app.route("/api/folders", methods=["GET"])
@login_required
def api_folders():
    data_dir = env.cellxgene_data
    folders = []
    if data_dir and os.path.isdir(data_dir):
        for entry in sorted(os.listdir(data_dir)):
            full = os.path.join(data_dir, entry)
            if os.path.isdir(full) and not entry.startswith(".") and not entry.endswith(annotations_suffix):
                folders.append(entry)
    resp = jsonify(folders)
    set_no_cache(resp)
    return resp


def _get_source(name):
    """Resolve source by name, falling back to default."""
    if name:
        return matching_source(name)
    return default_item_source or item_sources[0]


def _source_full_path(source, descriptor):
    """Call source.full_path if available (FileItemSource), else None."""
    fp = getattr(source, "full_path", None)
    return fp(descriptor) if fp else None


@app.route("/api/dataset/<path:descriptor>/launch", methods=["POST"])
@login_required
def api_launch(descriptor):
    descriptor = urllib.parse.unquote(descriptor)
    src = _get_source(request.args.get("source_name"))
    view_url = url_for("do_view", path=descriptor, source_name=src.name, _external=False)
    return jsonify({"ok": True, "redirect": view_url})


@app.route("/api/dataset/<path:descriptor>/terminate", methods=["POST"])
def api_terminate(descriptor):
    key = get_cache_key(descriptor)
    match = cache.check_entry(key)
    if match is not None:
        match.terminate()
    for entry in cache.find_entries_by_h5ad(key.h5ad_item.descriptor):
        entry.terminate()
    return jsonify({"ok": True})


@app.route("/api/dataset/<path:descriptor>/relaunch", methods=["POST"])
def api_relaunch(descriptor):
    key = get_cache_key(descriptor)
    match = cache.check_entry(key)
    if match is not None:
        match.terminate()
    for entry in cache.find_entries_by_h5ad(key.h5ad_item.descriptor):
        entry.terminate()
    src = _get_source(request.args.get("source_name"))
    view_url = url_for("do_view", path=descriptor, source_name=src.name, _external=False)
    return jsonify({"ok": True, "redirect": view_url})


@app.route("/api/dataset/<path:descriptor>/delete", methods=["POST"])
@login_required
def api_delete(descriptor):
    descriptor = urllib.parse.unquote(descriptor)
    src = _get_source(request.args.get("source_name"))
    lookup = src.lookup(descriptor)
    if lookup is None:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404

    key = CacheKey.for_lookup(src, lookup)
    match = cache.check_entry(key)
    if match is not None:
        match.terminate()

    full_path = _source_full_path(src, descriptor)
    if full_path:
        try:
            os.remove(full_path)
        except OSError as e:
            return jsonify({"ok": False, "error": str(e)}), 500

        ann_dir = _source_full_path(src, src.get_annotations_subpath(lookup.h5ad_item))
        if ann_dir and os.path.isdir(ann_dir):
            shutil.rmtree(ann_dir, ignore_errors=True)

    return jsonify({"ok": True})


@app.route("/api/dataset/<path:descriptor>/annotations/new", methods=["POST"])
@login_required
def api_new_annotation(descriptor):
    descriptor = urllib.parse.unquote(descriptor)
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Annotation name required"}), 400

    src = _get_source(request.args.get("source_name"))
    lookup = src.lookup(descriptor)
    if lookup is None:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404

    from cellxgene_gateway.dir_util import ensure_dir_exists
    ann_subpath = src.get_annotations_subpath(lookup.h5ad_item)
    ann_dir = _source_full_path(src, ann_subpath)
    if ann_dir:
        ensure_dir_exists(ann_dir)
        ann_file = os.path.join(ann_dir, name + ".csv")
        if os.path.exists(ann_file):
            return jsonify({"ok": False, "error": "Annotation already exists"}), 409
        with open(ann_file, "w") as f:
            f.write("")
        return jsonify({"ok": True, "name": name + ".csv"})
    else:
        return jsonify({"ok": False, "error": "Source does not support annotations"}), 400


@app.route("/api/dataset/<path:descriptor>/embeddings", methods=["GET"])
@login_required
def api_embeddings(descriptor):
    descriptor = urllib.parse.unquote(descriptor)
    src = _get_source(request.args.get("source_name"))
    full_path = _source_full_path(src, descriptor)
    if not full_path or not os.path.isfile(full_path):
        return jsonify({"ok": False, "error": "Dataset not found"}), 404
    try:
        import h5py
        with h5py.File(full_path, "r") as f:
            obsm = f.get("obsm")
            embeddings = sorted(k for k in obsm.keys() if k.startswith("X_")) if obsm else []
        embeddings = [k[2:] for k in embeddings]
        return jsonify({"ok": True, "embeddings": embeddings})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/dataset/<path:descriptor>/config", methods=["GET"])
@login_required
def api_get_config(descriptor):
    descriptor = urllib.parse.unquote(descriptor)
    src = _get_source(request.args.get("source_name"))
    full_path = _source_full_path(src, descriptor)
    if not full_path:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404
    cfg = {"default_embedding": None}
    cfg_path = vipconfig_path(full_path)
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except Exception:
            pass
    return jsonify({"ok": True, **cfg})


@app.route("/api/dataset/<path:descriptor>/config", methods=["POST"])
@login_required
def api_set_config(descriptor):
    descriptor = urllib.parse.unquote(descriptor)
    src = _get_source(request.args.get("source_name"))
    full_path = _source_full_path(src, descriptor)
    if not full_path:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404
    data = request.get_json(silent=True) or {}
    cfg_path = vipconfig_path(full_path)
    cfg = {}
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path) as f:
                cfg = json.load(f)
        except Exception:
            pass
    if "default_embedding" in data:
        cfg["default_embedding"] = data["default_embedding"]
    try:
        with open(cfg_path, "w") as f:
            json.dump(cfg, f)
    except PermissionError:
        return jsonify({"ok": False, "error": "Permission denied - check directory permissions"}), 403
    return jsonify({"ok": True, **cfg})


@app.route("/api/dataset/<path:descriptor>/annotations/<name>/bake", methods=["POST"])
@login_required
def api_bake_annotation(descriptor, name):
    descriptor = urllib.parse.unquote(descriptor)
    src = _get_source(request.args.get("source_name"))
    lookup = src.lookup(descriptor)
    if lookup is None:
        return jsonify({"ok": False, "error": "Dataset not found"}), 404

    full_path = _source_full_path(src, descriptor)
    if not full_path or not os.path.isfile(full_path):
        return jsonify({"ok": False, "error": "Dataset file not found"}), 404

    ann_subpath = src.get_annotations_subpath(lookup.h5ad_item) if env.enable_annotations else None
    if not ann_subpath:
        return jsonify({"ok": False, "error": "Annotations not supported"}), 400

    ann_dir = _source_full_path(src, ann_subpath)
    ann_file = os.path.join(ann_dir, name)
    if not ann_file.endswith(".csv"):
        ann_file += ".csv"
    if not os.path.isfile(ann_file):
        return jsonify({"ok": False, "error": "Annotation file not found"}), 404

    key = CacheKey.for_lookup(src, lookup)
    match = cache.check_entry(key)
    if match is not None:
        match.terminate()
    for entry in cache.find_entries_by_h5ad(key.h5ad_item.descriptor):
        entry.terminate()

    try:
        import pandas as pd
        import anndata

        ann_df = pd.read_csv(ann_file, index_col=0)
        adata = anndata.read_h5ad(full_path)

        for col in ann_df.columns:
            adata.obs[col] = ann_df[col]

        adata.write_h5ad(full_path)

        os.remove(ann_file)
        gene_sets_file = ann_file.replace(".csv", "_gene_sets.csv")
        if os.path.isfile(gene_sets_file):
            os.remove(gene_sets_file)

        if ann_dir and os.path.isdir(ann_dir) and not os.listdir(ann_dir):
            os.rmdir(ann_dir)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/metadata/ip_address", methods=["GET"])
def ip_address():
    resp = make_response(env.ip)
    return set_no_cache(resp)


# ---------------------------------------------------------------------------
# Folder management API
# ---------------------------------------------------------------------------

def _data_dir():
    return env.cellxgene_data


def _subfolder_path(subfolder):
    """Resolve a subfolder name to an absolute path in the data directory."""
    base = _data_dir()
    if not subfolder:
        return base
    return os.path.join(base, subfolder)


@app.route("/api/folders/new", methods=["POST"])
@admin_required
def api_create_folder():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "error": "Folder name required"}), 400
    if "/" in name or "\\" in name:
        return jsonify({"ok": False, "error": "Folder name cannot contain slashes"}), 400
    folder_path = os.path.join(_data_dir(), name)
    try:
        os.makedirs(folder_path, exist_ok=True)
        return jsonify({"ok": True, "folder": name})
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/datasets/move", methods=["POST"])
@admin_required
def api_move_dataset():
    data = request.get_json(silent=True) or {}
    descriptor = data.get("descriptor", "").strip()
    target_folder = data.get("target_folder", "").strip()
    source_name = data.get("source", "")
    if not descriptor:
        return jsonify({"ok": False, "error": "Dataset descriptor required"}), 400

    src = _get_source(source_name)
    attrs = ["full_path", "get_annotations_subpath"]
    if not all(hasattr(src, a) for a in attrs):
        return jsonify({"ok": False, "error": "Source does not support move"}), 400

    full_path = src.full_path(descriptor)
    if not full_path or not os.path.isfile(full_path):
        return jsonify({"ok": False, "error": "Dataset file not found"}), 404

    target_dir = _subfolder_path(target_folder)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    fname = os.path.basename(full_path)
    dest = os.path.join(target_dir, fname)
    if os.path.exists(dest):
        return jsonify({"ok": False, "error": "A dataset with that name already exists in the target folder"}), 409

    lookup = src.lookup(descriptor)
    ann_subpath = None
    ann_dir = None
    if lookup:
        key = CacheKey.for_lookup(src, lookup)
        match = cache.check_entry(key)
        if match is not None:
            match.terminate()
        if env.enable_annotations:
            ann_subpath = src.get_annotations_subpath(lookup.h5ad_item)
            ann_dir = src.full_path(ann_subpath) if ann_subpath else None

    try:
        shutil.move(full_path, dest)
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    if ann_dir and os.path.isdir(ann_dir):
        dest_ann_dir = os.path.join(target_dir, os.path.basename(ann_dir))
        try:
            shutil.move(ann_dir, dest_ann_dir)
        except OSError:
            pass

    new_desc = os.path.join(target_folder, fname) if target_folder else fname
    return jsonify({"ok": True, "new_descriptor": new_desc})


# ---------------------------------------------------------------------------
# Admin API endpoints
# ---------------------------------------------------------------------------

@app.route("/admin")
@login_required
def admin_page():
    if not session.get("is_admin"):
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    return render_template("admin.html", username=session.get("username", ""))


@app.route("/api/admin/users", methods=["GET"])
@admin_required
def api_admin_list_users():
    users = models.list_users()
    return jsonify({"ok": True, "users": users})


@app.route("/api/admin/users", methods=["POST"])
@admin_required
def api_admin_create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400
    ok = models.create_user(username, password, is_admin=False)
    if not ok:
        return jsonify({"ok": False, "error": "Username already exists"}), 409
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_admin_delete_user(user_id):
    if user_id == session["user_id"]:
        return jsonify({"ok": False, "error": "Cannot delete yourself"}), 400
    models.delete_user(user_id)
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:user_id>/password", methods=["PUT"])
@admin_required
def api_admin_set_password(user_id):
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    if not password:
        return jsonify({"ok": False, "error": "Password required"}), 400
    models.update_password(user_id, password)
    return jsonify({"ok": True})


@app.route("/api/admin/users/<int:user_id>/permissions", methods=["GET"])
@admin_required
def api_admin_get_permissions(user_id):
    folders = models.get_user_permissions(user_id)
    return jsonify({"ok": True, "folders": folders})


@app.route("/api/admin/users/<int:user_id>/permissions", methods=["PUT"])
@admin_required
def api_admin_set_permissions(user_id):
    data = request.get_json(silent=True) or {}
    folders = data.get("folders", [])
    models.set_user_permissions(user_id, folders)
    return jsonify({"ok": True})


def start_pruner_thread():
    pruner = PruneProcessCache(cache)
    # Run the pruner as a daemon thread so it won't block interpreter
    # shutdown (for example when Ctrl-C is used in the main thread).
    # This avoids "Exception ignored in: <module 'threading'...>" at exit.
    background_thread = Thread(target=pruner, daemon=True)
    background_thread.start()


def launch():
    atexit.register(models.checkpoint_db)
    start_pruner_thread()

    app.extensions.setdefault("cellxgene_gateway", {})[
        "launchtime"
    ] = current_time_stamp()
    app.run(host="0.0.0.0", port=env.gateway_port, debug=False)


app.extensions.setdefault("cellxgene_gateway", {})["launchtime"] = None


def main():
    """CLI entry point for Flask development server."""
    launch()


if __name__ == "__main__":
    main()
