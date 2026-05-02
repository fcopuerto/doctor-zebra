"""
Doctor Zebra – main application entry point.

Run as a standalone Flask development server::

    flask --app app run

Or as a native desktop application via pywebview::

    python app.py
"""
import datetime
import json
import os
import threading

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from config import WINDOW_HEIGHT, WINDOW_TITLE, WINDOW_WIDTH
from modules import cache, printer, profiles, zpl_templates

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "doctor-zebra-dev-secret")


@app.template_filter("datetimefmt")
def _datetimefmt(ts):
    """Convert a Unix timestamp (int/float) to a human-readable string."""
    try:
        return datetime.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(ts)


# ===========================================================================
# Print / Index
# ===========================================================================


@app.route("/")
def index():
    profile_list = profiles.list_profiles()
    selected = request.args.get("profile") or (profile_list[0] if profile_list else None)
    profile = profiles.get_profile(selected) if selected else None

    variables = []
    template_content = ""
    if profile and profile.get("template"):
        template_content = zpl_templates.get_template(profile["template"]) or ""
        variables = printer.extract_variables(template_content)

    # Build lookup options for fields that declare one
    lookup_options: dict[str, list] = {}
    if profile:
        for field in profile.get("fields", []):
            lk = field.get("lookup")
            if lk:
                lookup_options[field["name"]] = cache.get_lookup(lk) or []

    return render_template(
        "index.html",
        profiles=profile_list,
        selected=selected,
        profile=profile,
        variables=variables,
        template_content=template_content,
        lookup_options=lookup_options,
    )


@app.route("/print", methods=["POST"])
def do_print():
    profile_name = request.form.get("profile", "")
    profile = profiles.get_profile(profile_name)
    if not profile:
        flash("Perfil no encontrado.", "danger")
        return redirect(url_for("index", profile=profile_name))

    template_name = profile.get("template", "")
    template_content = zpl_templates.get_template(template_name)
    if not template_content:
        flash("Plantilla ZPL no encontrada.", "danger")
        return redirect(url_for("index", profile=profile_name))

    # Collect field values from the submitted form (exclude meta-fields)
    meta_keys = {"profile", "copies"}
    data = {k: v for k, v in request.form.items() if k not in meta_keys}

    zpl = printer.render_template(template_content, data)

    host = profile["printer"]["host"]
    port = int(profile["printer"].get("port", 9100))
    copies = max(1, int(request.form.get("copies", 1)))

    try:
        for _ in range(copies):
            printer.send_zpl(host, port, zpl)
        flash(
            f"{copies} etiqueta(s) enviada(s) a {host}:{port}.",
            "success",
        )
    except OSError as exc:
        flash(f"Error de conexión con la impresora: {exc}", "danger")

    return redirect(url_for("index", profile=profile_name))


# ===========================================================================
# Profiles
# ===========================================================================


@app.route("/profiles")
def profiles_list():
    return render_template("profiles/list.html", profiles=profiles.list_profiles())


@app.route("/profiles/new", methods=["GET", "POST"])
def profile_new():
    return _profile_form(None)


@app.route("/profiles/<name>/edit", methods=["GET", "POST"])
def profile_edit(name):
    return _profile_form(name)


@app.route("/profiles/<name>/delete", methods=["POST"])
def profile_delete(name):
    profiles.delete_profile(name)
    flash(f"Perfil '{name}' eliminado.", "success")
    return redirect(url_for("profiles_list"))


def _profile_form(name):
    """Shared GET/POST handler for create and edit profile views."""
    if request.method == "POST":
        new_name = request.form.get("name", "").strip()
        try:
            data = {
                "name": request.form.get("display_name", new_name),
                "printer": {
                    "host": request.form.get("printer_host", ""),
                    "port": int(request.form.get("printer_port", 9100)),
                },
                "template": request.form.get("template", ""),
                "fields": json.loads(request.form.get("fields_json", "[]")),
            }
            profiles.save_profile(new_name, data)
            flash(f"Perfil '{new_name}' guardado.", "success")
            return redirect(url_for("profiles_list"))
        except (ValueError, json.JSONDecodeError) as exc:
            flash(f"Error al guardar el perfil: {exc}", "danger")

    profile_data = profiles.get_profile(name) if name else {}
    return render_template(
        "profiles/edit.html",
        name=name,
        profile=profile_data,
        templates=zpl_templates.list_templates(),
    )


# ===========================================================================
# ZPL Templates
# ===========================================================================


@app.route("/templates")
def templates_list():
    items = []
    for tname in zpl_templates.list_templates():
        content = zpl_templates.get_template(tname) or ""
        items.append(
            {
                "name": tname,
                "variables": printer.extract_variables(content),
                "preview": content[:120],
            }
        )
    return render_template("zpl_templates/list.html", templates=items)


@app.route("/templates/new", methods=["GET", "POST"])
def template_new():
    return _template_form(None)


@app.route("/templates/<name>/edit", methods=["GET", "POST"])
def template_edit(name):
    return _template_form(name)


@app.route("/templates/<name>/delete", methods=["POST"])
def template_delete(name):
    zpl_templates.delete_template(name)
    flash(f"Plantilla '{name}' eliminada.", "success")
    return redirect(url_for("templates_list"))


def _template_form(name):
    if request.method == "POST":
        new_name = request.form.get("name", "").strip()
        content = request.form.get("content", "")
        try:
            zpl_templates.save_template(new_name, content)
            flash(f"Plantilla '{new_name}' guardada.", "success")
            return redirect(url_for("templates_list"))
        except ValueError as exc:
            flash(str(exc), "danger")

    content = zpl_templates.get_template(name) if name else ""
    variables = printer.extract_variables(content or "")
    return render_template(
        "zpl_templates/edit.html",
        name=name,
        content=content or "",
        variables=variables,
    )


# ===========================================================================
# Offline Lookup Cache
# ===========================================================================


@app.route("/cache")
def cache_list():
    return render_template("cache/list.html", lookups=cache.list_lookups())


@app.route("/cache/new", methods=["GET", "POST"])
def cache_new():
    return _cache_form(None)


@app.route("/cache/<name>/edit", methods=["GET", "POST"])
def cache_edit(name):
    return _cache_form(name)


@app.route("/cache/<name>/delete", methods=["POST"])
def cache_delete(name):
    cache.delete_lookup(name)
    flash(f"Lookup '{name}' eliminado.", "success")
    return redirect(url_for("cache_list"))


@app.route("/cache/<name>/refresh", methods=["POST"])
def cache_refresh(name):
    url = request.form.get("source_url", "").strip()
    if not url:
        # Try to use the stored source_url
        all_lk = cache.list_lookups()
        entry = next((lk for lk in all_lk if lk["name"] == name), None)
        if entry:
            url = entry.get("source_url") or ""
    if not url:
        flash("No hay URL de origen configurada.", "danger")
        return redirect(url_for("cache_edit", name=name))
    try:
        data = cache.refresh_lookup(name, url)
        count = len(data) if isinstance(data, list) else 1
        flash(f"Lookup '{name}' actualizado: {count} registros.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(f"Error al actualizar: {exc}", "danger")
    return redirect(url_for("cache_edit", name=name))


def _cache_form(name):
    if request.method == "POST":
        action = request.form.get("action", "save")
        new_name = request.form.get("name", "").strip()
        source_url = request.form.get("source_url", "").strip()
        raw_data = request.form.get("data_json", "[]").strip()

        if action == "refresh" and source_url:
            try:
                data = cache.refresh_lookup(new_name, source_url)
                count = len(data) if isinstance(data, list) else 1
                flash(f"Lookup '{new_name}' importado: {count} registros.", "success")
                return redirect(url_for("cache_list"))
            except Exception as exc:  # noqa: BLE001
                flash(f"Error al importar: {exc}", "danger")
        else:
            try:
                parsed = json.loads(raw_data)
                cache.set_lookup(new_name, parsed, source_url=source_url or None)
                flash(f"Lookup '{new_name}' guardado.", "success")
                return redirect(url_for("cache_list"))
            except json.JSONDecodeError as exc:
                flash(f"JSON inválido: {exc}", "danger")

    existing_data = None
    source_url = ""
    if name:
        existing_data = cache.get_lookup(name)
        all_lk = cache.list_lookups()
        entry = next((lk for lk in all_lk if lk["name"] == name), None)
        source_url = (entry or {}).get("source_url") or ""

    return render_template(
        "cache/edit.html",
        name=name,
        data_json=json.dumps(existing_data, indent=2, ensure_ascii=False)
        if existing_data is not None
        else "[]",
        source_url=source_url,
    )


# ===========================================================================
# JSON API (used by the JS autocomplete / autofill)
# ===========================================================================


@app.route("/api/lookup/<name>/search")
def api_lookup_search(name):
    query = request.args.get("q", "")
    fields_param = request.args.get("fields", "")
    fields = [f.strip() for f in fields_param.split(",") if f.strip()] or None
    results = cache.search_lookup(name, query, fields=fields)
    return jsonify(results)


@app.route("/api/templates/<name>/variables")
def api_template_variables(name):
    content = zpl_templates.get_template(name) or ""
    return jsonify(printer.extract_variables(content))


# ===========================================================================
# Desktop entry point
# ===========================================================================


def _start_flask(port: int = 5000) -> None:
    app.run(host="127.0.0.1", port=port, use_reloader=False, debug=False)


def main() -> None:
    """Launch Doctor Zebra as a native desktop window via pywebview."""
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        print(
            "pywebview is not installed.  Running as a plain Flask server at "
            "http://127.0.0.1:5000 – open that URL in your browser."
        )
        app.run(host="127.0.0.1", port=5000, debug=True)
        return

    port = 5000
    server_thread = threading.Thread(target=_start_flask, args=(port,), daemon=True)
    server_thread.start()

    window = webview.create_window(
        WINDOW_TITLE,
        f"http://127.0.0.1:{port}",
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        resizable=True,
    )
    webview.start()


if __name__ == "__main__":
    main()
