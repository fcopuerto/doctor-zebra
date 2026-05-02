<div align="center">
  <img src="static/logo.svg" alt="Comandante Zebra" width="120" height="120">
  <h1>Comandante Zebra</h1>
  <p><strong>Imprime etiquetas en impresoras Zebra (ZPL) desde una app de escritorio</strong> con plantillas editables, búsqueda de datos contra fuentes externas con caché offline, y soporte multi-perfil.</p>

  <p>
    <a href="https://github.com/fcopuerto/comandante_zebra/actions/workflows/build-windows.yml">
      <img alt="Build Windows" src="https://github.com/fcopuerto/comandante_zebra/actions/workflows/build-windows.yml/badge.svg">
    </a>
    <a href="https://github.com/fcopuerto/comandante_zebra/releases/latest">
      <img alt="Latest release" src="https://img.shields.io/github/v/release/fcopuerto/comandante_zebra?include_prereleases&sort=semver">
    </a>
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
    <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  </p>
</div>

---

## Qué es

Comandante Zebra es una pequeña aplicación de escritorio (Flask + pywebview) para tiendas y entornos industriales que necesitan **imprimir etiquetas Zebra (ZPL)** de forma cómoda, sin depender del software propietario de Zebra ni de una conexión constante a la base de datos.

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

1. Ve a [Releases](https://github.com/fcopuerto/comandante_zebra/releases/latest) y descarga `ComandanteZebra.exe`.
2. Ejecútalo. La primera vez creará `C:\Users\<tu-usuario>\.comandante_zebra\` con un perfil `default` vacío.
3. Lanza el asistente desde **Settings → Wizard** y configura tu impresora y conexión.

> Si no hay un release publicado todavía, puedes bajar el último build de la pestaña **Actions** (artifact `ComandanteZebra-windows`).

#### Aviso de Windows SmartScreen / Defender

Como el `.exe` no está firmado con un certificado de _code signing_ comercial,
Windows SmartScreen mostrará el aviso **"Windows protected your PC"** la
primera vez que lo ejecutes. Es normal para binarios nuevos sin reputación.
Para abrirlo:

1. Click en **More info** (Más información) en el diálogo.
2. Click en **Run anyway** (Ejecutar de todas formas).

Esto lo "aprenderás" Windows tras la primera ejecución y dejará de
preguntar. Para verificar que descargaste exactamente el `.exe` que
construyó nuestro CI, cada release adjunta también un archivo
`ComandanteZebra.exe.sha256`. Compara el hash en PowerShell:

```powershell
Get-FileHash ComandanteZebra.exe -Algorithm SHA256
# Debe coincidir con el contenido de ComandanteZebra.exe.sha256
```

### macOS / Linux

Por ahora solo se publican binarios de Windows. En macOS puedes correrlo desde fuente (ver más abajo) o construir el `.app` localmente con `pyinstaller build_desktop.spec`.

## Ejecutar desde fuente

El proyecto se gestiona con [**uv**](https://docs.astral.sh/uv/) (rápido,
con lockfile, reproducible). Si no lo tienes:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # macOS / Linux
# Windows (PowerShell):
#   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Después:

```bash
git clone https://github.com/fcopuerto/comandante_zebra.git
cd comandante_zebra

# Runtime + driver SQL Server pure-Python (recomendado):
uv sync --extra mssql-pure

# Lanzar la app de escritorio:
uv run python desktop.py
```

Esto crea automáticamente un `.venv/` con la versión correcta de Python e
instala las dependencias del lockfile (`uv.lock`).

Solo el servidor web (sin ventana nativa, útil para desarrollo en navegador):

```bash
uv run python app.py
# luego abre http://127.0.0.1:5000
```

### Extras opcionales

| Para…                                    | Comando                                |
|------------------------------------------|----------------------------------------|
| SQL Server pure-Python (sin drivers MS)  | `uv sync --extra mssql-pure`           |
| SQL Server con Microsoft ODBC Driver 18  | `uv sync --extra mssql-odbc`           |
| Empaquetar con PyInstaller               | `uv sync --group build`                |
| Todo lo anterior                         | `uv sync --extra mssql-pure --group build` |

> **Si prefieres pip clásico:** los archivos `requirements.txt`,
> `requirements-mssql-pure.txt` y `requirements-mssql-odbc.txt` siguen
> funcionando como antes.

## Construir el ejecutable

El `.exe` de Windows se construye automáticamente en GitHub Actions con cada
push a `main` (workflow [`build-windows.yml`](.github/workflows/build-windows.yml)).
Para construirlo manualmente en cualquier plataforma:

```bash
uv sync --extra mssql-pure --group build
uv run pyinstaller --noconfirm --clean build_desktop.spec
# Salida:
#   dist/ComandanteZebra.exe   (Windows)
#   dist/ComandanteZebra.app   (macOS)
```

PyInstaller **no** hace cross-compile: para generar el `.exe` necesitas
ejecutarlo en Windows (o usar el workflow de Actions).

## Red local: descubrimiento y compartir entre instancias

Comandante Zebra detecta automáticamente otras instancias de la misma app
en la red local (vía mDNS / Bonjour) y permite **descargar plantillas y
definiciones de conexiones** entre ellas. Útil cuando varias tiendas o
máquinas comparten el mismo catálogo de etiquetas.

### Cómo funciona

- Cada instancia se anuncia como `_comandante-zebra._tcp.local.` en su LAN.
- En **Configuración → Red** ves tu propio identificador, IP, perfil y un
  **PIN de 6 dígitos** generado al primer arranque.
- Para descargar de un peer, abres su tarjeta, introduces su PIN y
  seleccionas qué quieres importar.
- Por defecto se comparten **plantillas** (.zpl + sidecar). Las
  **conexiones** (servidor / base de datos) requieren un toggle aparte y
  **siempre viajan sin contraseñas** — el receptor introduce sus propias
  credenciales después de importar.

### Si no aparecen otros equipos

La pantalla **Configuración → Red → Diagnóstico** muestra el estado y
te guía con consejos por cada problema detectado. Las causas habituales:

- **Firewall** bloqueando UDP/5353. En Windows: permitir Comandante Zebra
  (o `python.exe`) en Windows Defender Firewall — la red Privada basta.
- **Bonjour Service** no instalado en Windows. Solución: instalar
  "Bonjour Print Services" de Apple.
- Otra instancia en una **subred distinta** — mDNS es link-local, no
  cruza routers.

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
~/.comandante_zebra/
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
