from flask import Blueprint, current_app, jsonify

dev_bp = Blueprint("_dev", __name__)

@dev_bp.get("/_routes")
def list_routes():
    """List all GET routes (for screenshot pipeline discovery)."""
    routes = []
    for rule in current_app.url_map.iter_rules():
        if "GET" not in (rule.methods or set()):
            continue
        if "<" in rule.rule:  # skip routes with path params
            continue
        if rule.rule.startswith("/static"):
            continue
        routes.append({"rule": rule.rule, "endpoint": rule.endpoint})
    return jsonify(sorted(routes, key=lambda r: r["rule"]))