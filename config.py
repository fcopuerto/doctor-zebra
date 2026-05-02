"""
Centralised path and application constants for Doctor Zebra.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
PROFILES_DIR = os.path.join(DATA_DIR, "profiles")
TEMPLATES_DIR = os.path.join(DATA_DIR, "zpl_templates")
CACHE_DB = os.path.join(DATA_DIR, "cache.db")

# Default TCP port used by Zebra printers
DEFAULT_PRINTER_PORT = 9100

# Application window dimensions when running inside pywebview
WINDOW_TITLE = "Doctor Zebra"
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
