# Changelog

Todos los cambios relevantes de Doctor Zebra se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado adopta [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.1.1] - 2026-05-02

### Arreglado

- El `.exe` de Windows no incluía ningún driver de SQL Server, así que las
  conexiones MSSQL fallaban con `No module named pymssql`. Ahora la build
  de Windows empaqueta `pymssql` (pure-Python, sin dependencias del sistema)
  y la pantalla **Settings → Database connections** lo refleja.
- En el `.exe`, la pantalla de conexiones ya no sugiere comandos
  `pip install` (que no aplican fuera del entorno de desarrollo). En su
  lugar muestra qué drivers vienen empaquetados y qué requiere cada uno.

## [0.1.0] - 2026-05-02

Primera versión pública. La app ya es usable de extremo a extremo y se
distribuye como `.exe` autónomo para Windows.

### Añadido

- App de escritorio Flask + pywebview empaquetable con PyInstaller.
- Impresión ZPL contra impresoras Zebra (USB / spooler de Windows o IP).
- Editor y previsualización de plantillas ZPL con campos parametrizables.
- Conector de datos para SQL Server (ODBC y pure-Python) con arquitectura
  de _datasources_ extensible.
- Caché offline de lookups en SQLite con refresco en segundo plano —
  permite imprimir sin conexión.
- Soporte multi-perfil (folder-per-profile) con cambio mediante reinicio.
- Asistente inicial (Wizard) para configurar conexión, impresora y
  plantillas paso a paso.
- Tema claro/oscuro con detección automática del sistema.
- Logo e iconos propios (`.ico` Windows, `.icns` macOS, SVG web).
- Workflow de GitHub Actions que construye `DoctorZebra.exe` en cada push
  a `main` y lo adjunta a un GitHub Release cuando se publica un tag `v*`.

### Notas de migración

- El directorio de datos del usuario se llama ahora `~/.doctor_zebra/`.
  Las instalaciones previas que usaban `~/.zebra_labels/` se renombran
  automáticamente en el primer arranque sin perder datos.

[Unreleased]: https://github.com/fcopuerto/doctor-zebra/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/fcopuerto/doctor-zebra/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/fcopuerto/doctor-zebra/releases/tag/v0.1.0
