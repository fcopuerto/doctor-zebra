# Changelog

Todos los cambios relevantes de Doctor Zebra se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado adopta [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.2.1] - 2026-05-02

### Añadido

- **Top items** en el Dashboard: ranking de los SKUs / claves de lookup
  más impresos (10 primeros). Cada impresión captura automáticamente el
  valor del primer campo de tipo `lookup` del formulario y lo guarda en
  `lookup_key`, así que no hay que tocar plantillas existentes.
- Las impresiones desde plantillas sin campo lookup quedan con
  `lookup_key=NULL` y simplemente no aparecen en el ranking.

## [0.2.0] - 2026-05-02

Reorganización del nav y primera versión del Dashboard con métricas reales.

### Añadido

- **Sidebar** dividido en dos secciones: **Operations** (Print, Dashboard,
  History) y **Administration** (Settings). El asistente de configuración
  se promociona como CTA dentro de Settings en vez de ocupar nav primario.
- Pantalla **`/dashboard`** con:
  - KPIs: etiquetas impresas hoy / últimos 7 días / últimos 30 días / total.
  - Gráfico SVG inline de actividad diaria (últimos 30 días).
  - Top 5 plantillas, top 5 tamaños (`mm × mm`) y top 5 impresoras, con
    barras proporcionales.
  - Tabla de errores recientes (impresiones que fallaron).
- Captura enriquecida en cada impresión: `copies`, `printer_name`, `status`,
  `error_message`, `label_width_mm`, `label_height_mm`, `lookup_key` y
  `profile_name`. Las dimensiones se extraen de los comandos `^PW` / `^LL`
  del ZPL renderizado (asumiendo 203 dpi, que es el estándar Zebra).
- Las impresiones que fallan también se registran ahora (con
  `status='error'`) para que el dashboard pueda mostrarlas.

### Cambiado

- El esquema de `label_prints` se migra de forma aditiva con `ALTER TABLE`,
  así que las instalaciones existentes mantienen todos los registros.
- Añadido índice por `printed_at` para acelerar las consultas de stats.

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

[Unreleased]: https://github.com/fcopuerto/doctor-zebra/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/fcopuerto/doctor-zebra/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/fcopuerto/doctor-zebra/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/fcopuerto/doctor-zebra/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/fcopuerto/doctor-zebra/releases/tag/v0.1.0
