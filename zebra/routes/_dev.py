"""Dev-only endpoint to list routes for the screenshot pipeline.

Only registered when ZEBRA_DEV_ROUTES=1 in the environment.
Safe to ship: it does nothing unless that env var is set.
"""

import os
from flask import Blueprint, current_app, jsonify

dev_bp = Blueprint("_dev", __name__)


@dev_bp.get("/_routes")
def list_routes():
    """Return all parameter-free GET routes as JSON."""
    routes = []
    for rule in current_app.url_map.iter_rules():
        methods = rule.methods or set()
        if "GET" not in methods:
            continue
        if "<" in rule.rule:                # skip routes with path params
            continue
        if rule.rule.startswith("/static"):
            continue
        if rule.rule.startswith("/_"):      # skip dev endpoints themselves
            continue
        routes.append({"rule": rule.rule, "endpoint": rule.endpoint})
    return jsonify(sorted(routes, key=lambda r: r["rule"]))


def register_if_enabled(app):
    """Call this from create_app(). No-op unless ZEBRA_DEV_ROUTES=1."""
    if os.environ.get("ZEBRA_DEV_ROUTES") == "1":
        app.register_blueprint(dev_bp)
