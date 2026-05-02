<div align="center">
  <img src="static/logo.svg" alt="Doctor Zebra" width="120" height="120">
  <h1>Doctor Zebra</h1>
  <p><strong>Imprime etiquetas en impresoras Zebra (ZPL) desde una app de escritorio</strong> con plantillas editables, búsqueda de datos contra fuentes externas con caché offline, y soporte multi-perfil.</p>

  <p>
    <a href="https://github.com/fcopuerto/doctor-zebra/actions/workflows/build-windows.yml">
      <img alt="Build Windows" src="https://github.com/fcopuerto/doctor-zebra/actions/workflows/build-windows.yml/badge.svg">
    </a>
    <a href="https://github.com/fcopuerto/doctor-zebra/releases/latest">
      <img alt="Latest release" src="https://img.shields.io/github/v/release/fcopuerto/doctor-zebra?include_prereleases&sort=semver">
    </a>
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
    <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  </p>
</div>

---

## Qué es

Doctor Zebra es una pequeña aplicación de escritorio (Flask + pywebview) para tiendas y entornos industriales que necesitan **imprimir etiquetas Zebra (ZPL)** de forma cómoda, sin depender del software propietario de Zebra ni de una conexión constante a la base de datos.

Casos típicos:

- Imprimir etiquetas de producto a partir de un código (rellenando datos desde SQL Server, ERP, etc.).
- Tener varias **configuraciones independientes** (tienda A, tienda B, almacén) en el mismo binario.
- Seguir imprimiendo aunque se caiga la red: los lookups van contra una **caché local** que se sincroniza en segundo plano.

## Funcionalidades

- 🖨️ **Impresión ZPL directa** a impresoras Zebra (USB / spooler de Windows o IP).
- 📝 **Editor y previsualización** de plantillas ZPL con campos parametrizables.
- 🔌 **Datasources** conectables: hoy SQL Server (ODBC y pure-Python), arquitectura preparada para añadir más.
- ⚡ **Caché offline** de lookups en SQLite — imprime sin conexión, sincroniza cuando hay red.
- 👥 **Multi-perfil**: cada perfil es un directorio independiente con sus plantillas, configuración y base de datos.
- 🪄 **Asistente** inicial para configurar conexión, impresora y plantillas paso a paso.
- 🌓 Tema claro/oscuro.

## Capturas

> _Pendientes — añadir cuando estén las pantallas finales._

## Descarga

### Windows (recomendado)

1. Ve a [Releases](https://github.com/fcopuerto/doctor-zebra/releases/latest) y descarga `DoctorZebra.exe`.
2. Ejecútalo. La primera vez creará `C:\Users\<tu-usuario>\.doctor_zebra\` con un perfil `default` vacío.
3. Lanza el asistente desde **Settings → Wizard** y configura tu impresora y conexión.

> Si no hay un release publicado todavía, puedes bajar el último build de la pestaña **Actions** (artifact `DoctorZebra-windows`).

### macOS / Linux

Por ahora solo se publican binarios de Windows. En macOS puedes correrlo desde fuente (ver más abajo) o construir el `.app` localmente con `pyinstaller build_desktop.spec`.

## Ejecutar desde fuente

```bash
git clone https://github.com/fcopuerto/doctor-zebra.git
cd doctor-zebra

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
# Opcional (si vas a usar SQL Server con ODBC):
pip install -r requirements-mssql-odbc.txt

python desktop.py
```

Esto abre la ventana de la app apuntando a un servidor Flask local en `127.0.0.1:<puerto-libre>`.

Si solo quieres el servidor web (sin ventana nativa, p. ej. para desarrollo en navegador):

```bash
python app.py
# luego abre http://127.0.0.1:5000
```

## Construir el ejecutable

El `.exe` de Windows se construye automáticamente en GitHub Actions con cada push a `main` (workflow [`build-windows.yml`](.github/workflows/build-windows.yml)). Para construirlo manualmente en cualquier plataforma:

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean build_desktop.spec
# Salida:
#   dist/DoctorZebra.exe   (Windows)
#   dist/DoctorZebra.app   (macOS)
```

PyInstaller **no** hace cross-compile: para generar el `.exe` necesitas ejecutarlo en Windows (o usar el workflow de Actions).

## Arquitectura

```
desktop.py            ← wrapper de escritorio (pywebview)
app.py                ← entry point WSGI puro
zebra/                ← paquete principal
    __init__.py       ← create_app(base_dir=...)
    profiles.py       ← gestión multi-perfil (folder-per-profile)
    routes/           ← blueprints Flask (labels, config, templates)
    datasources/      ← conectores (mssql, registry de tipos)
    lookup_cache.py   ← caché SQLite de lookups (offline-first)
    cache_scheduler.py← refresco en background
    zpl.py / preview.py / printer.py
templates/, static/   ← UI (Jinja2 + JS vanilla)
seed_profiles/        ← perfil semilla que se copia al user dir en el primer run
build_desktop.spec    ← receta PyInstaller
.github/workflows/    ← CI (build Windows .exe)
```

### Datos del usuario

Cuando se ejecuta como `.exe`, los datos viven fuera del bundle para sobrevivir a actualizaciones:

```
~/.doctor_zebra/
├── profiles/
│   ├── .active
│   └── default/
│       ├── config.cfg
│       ├── secrets.cfg     (no se versiona)
│       ├── labels.db
│       └── templates_zpl/
└── app.log
```

Si actualizas desde una versión pre-rebrand que usaba `~/.zebra_labels/`, la app la renombra automáticamente en el primer arranque.

## Licencia

[MIT](LICENSE) © 2026 Fran Puerto
