#!/bin/sh
# Stable launcher on PATH. The PyInstaller one-file binary lives in
# /opt so the .desktop entry and `comandante-zebra` from a shell both
# resolve to the same place.
exec /opt/comandante-zebra/ComandanteZebra "$@"
