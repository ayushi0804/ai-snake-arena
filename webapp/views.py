"""Server-rendered page shells. Pages contain no per-user data, so they can be cached for offline use."""
from __future__ import annotations
from flask import Blueprint, Response, current_app, render_template, send_from_directory
from . import static_version, STATIC

bp = Blueprint("views", __name__)
PAGES = {"": ("index", "Home"), "play": ("play", "Play"), "dashboard": ("dashboard", "Dashboard"),
         "leaderboard": ("leaderboard", "Leaderboard"), "history": ("history", "History"),
         "benchmark": ("benchmark", "Benchmark Lab"), "settings": ("settings", "Settings"),
         "offline": ("offline", "Offline")}
PRECACHE_PAGES = ["/" + k for k in PAGES]


def _make(path, name, title):
    def view():
        return render_template(f"{name}.html", page=name, title=title)
    view.__name__ = f"page_{name}"
    bp.add_url_rule("/" + path, view_func=view)


for _p, (_n, _t) in PAGES.items():
    _make(_p, _n, _t)


@bp.route("/sw.js")
def service_worker():
    files = sorted(str(p.relative_to(STATIC)).replace("\\", "/") for p in STATIC.rglob("*")
                   if p.is_file() and not p.name.startswith("."))
    body = (STATIC / "sw.template.js").read_text(encoding="utf-8")
    body = (body.replace("__VERSION__", static_version())
                .replace("__PAGES__", repr(PRECACHE_PAGES).replace("'", '"'))
                .replace("__ASSETS__", repr(["/static/" + f for f in files if f != "sw.template.js"]).replace("'", '"')))
    r = Response(body, mimetype="text/javascript")
    r.headers["Cache-Control"] = "no-cache"          # always revalidate so updates are picked up
    r.headers["Service-Worker-Allowed"] = "/"
    return r


@bp.route("/manifest.webmanifest")
def manifest():
    r = send_from_directory(STATIC, "manifest.webmanifest", mimetype="application/manifest+json")
    r.headers["Cache-Control"] = "no-cache"
    return r
