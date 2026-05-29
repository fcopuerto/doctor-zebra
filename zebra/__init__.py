"""Application factory for Comandante Zebra."""

import logging
import time
from pathlib import Path

from flask import Flask, g, request

from zebra import discovery, i18n, network, printer, profiles, updater
from zebra.cache_scheduler import start_scheduler
from zebra.db import init_db
from zebra.lookup_cache import init_cache
from zebra.settings import Settings
from zebra.routes._dev import register_if_enabled as _register_dev_routes


LANG_COOKIE = 'comandante_zebra_lang'

__version__ = '1.1.0'

# Path to the package root (read-only assets when frozen with PyInstaller).
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
# Default writable base for profiles/, used when running from source.
BASE_DIR = PACKAGE_ROOT


def create_app(
    config_path: str | Path | None = None,
    db_path: str | Path | None = None,
    base_dir: str | Path | None = None,
) -> Flask:
    """Create the Flask app.

    ``base_dir`` is the writable root that holds ``profiles/`` (and any other
    user-mutable state). When running from source it defaults to the project
    root; when frozen with PyInstaller, ``desktop.py`` passes
    ``~/.comandante_zebra/`` so user data persists outside the bundle.
    """
    base = Path(base_dir) if base_dir else BASE_DIR

    app = Flask(
        'zebra',
        template_folder=str(PACKAGE_ROOT / 'templates'),
        static_folder=str(PACKAGE_ROOT / 'static'),
    )

    # Resolve which profile is active (creates profiles/default/ on first run
    # and migrates pre-profile data into it).
    profiles.bootstrap(base)
    paths = profiles.resolve_paths(base)
    app.config['PROFILE_NAME'] = paths['profile_name']
    app.config['PROFILE_DIR'] = str(paths['profile_dir'])
    app.config['BASE_DIR'] = str(base)

    settings = Settings(config_path or paths['config_path'])
    app.config['SETTINGS'] = settings
    app.config['DB_PATH'] = str(db_path or paths['db_path'])
    app.config['STARTED_AT'] = time.time()

    init_db(app.config['DB_PATH'])
    init_cache(app.config['DB_PATH'])
    i18n.load_all(PACKAGE_ROOT / 'i18n')
    network.init(base)
    updater.init(base)

    # Start mDNS discovery. The browser is always on so we can list
    # other peers on the LAN; we only publish ourselves once desktop.py
    # tells us which port Flask is listening on (via DISCOVERY_PORT).
    try:
        port = int(app.config.get('DISCOVERY_PORT') or 0)
    except (TypeError, ValueError):
        port = 0
    discovery.get_discovery().start(
        peer_name=network.peer_name(),
        version=__version__,
        profile=app.config.get('PROFILE_NAME', ''),
        port=port,
    )

    if app.config.get('AUTO_SYNC_CACHE', True):
        start_scheduler(app)

    from zebra.routes.config import bp as config_bp
    from zebra.routes.labels import bp as labels_bp
    from zebra.routes.network import bp as network_bp
    from zebra.routes.tmpl import bp as tmpl_bp
    app.register_blueprint(labels_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(network_bp)
    app.register_blueprint(tmpl_bp)


    # Needed for flash() messages.
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'zebra-labels-local'

    @app.before_request
    def _resolve_lang():
        g.lang = i18n.pick(
            request.cookies.get(LANG_COOKIE),
            request.headers.get('Accept-Language'),
            base_dir=Path(app.config['BASE_DIR']),
        )

    @app.context_processor
    def inject_printer_info():
        name = settings.default_printer
        status, color = printer.printer_status(name)
        return dict(
            active_printer=name,
            printer_status=status,
            status_color=color,
            active_profile=app.config.get('PROFILE_NAME', 'default'),
            app_version=__version__,
        )

    @app.context_processor
    def inject_i18n():
        lang = getattr(g, 'lang', i18n.DEFAULT_LANG)
        return dict(
            t=lambda key: i18n.translate(key, lang),
            lang=lang,
            available_langs=i18n.available(),
        )
    _register_dev_routes(app)
    logging.info('Zebra app initialized')
    return app
