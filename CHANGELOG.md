# Changelog

Todos los cambios relevantes de Comandante Zebra se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado adopta [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.6.0] - 2026-05-03

### Añadido

- **Descubrimiento P2P en la red local + intercambio de plantillas y
  conexiones entre instancias.** Nueva pestaña **Configuración → Red**.
  - mDNS / Bonjour: cada instancia se anuncia como
    `_comandante-zebra._tcp.local.` y descubre a las demás
    automáticamente al estar en la misma LAN. Funciona en macOS, Windows
    y Linux sin tocar el router.
  - Cada instancia muestra su nombre, IP, perfil activo y un **PIN de
    6 dígitos** generado al primer arranque. El nombre y los toggles de
    "qué comparto" son editables; el PIN se puede regenerar en cualquier
    momento.
  - **Pull-only con auth**: para descargar de un peer hay que introducir
    su PIN. Sin PIN no se ve nada.
  - **Por defecto se comparten plantillas** (inocuas, ZPL puro). Las
    **conexiones a base de datos** llevan un toggle aparte y, cuando se
    comparten, **viajan sin contraseñas** (el receptor introduce sus
    propias credenciales después de importar).
  - Modal de import: muestra qué tiene el peer, checkbox por item,
    "Importar selección" y resumen del resultado.
- Nuevas dependencias: `zeroconf>=0.130` (con `ifaddr`).
- Nuevo icono `i-network` en el sprite SVG.

### Detalles técnicos

- `zebra/discovery.py` — Singleton con publisher + browser. Se reinicia
  on demand cuando cambia el nombre del peer.
- `zebra/network.py` — Identidad persistida en `<base_dir>/network.json`.
  PIN sacado de `secrets.randbelow` y comparado con `compare_digest`.
- `zebra/routes/network.py` — Endpoints `/api/network/*` (UI local) y
  `/api/peer/*` (autenticados con PIN).
- `desktop.py` ahora notifica el puerto real de Flask al discovery vía
  `app.config['DISCOVERY_PORT']`, así el announcement mDNS lleva una
  dirección directamente accesible.

## [0.5.1] - 2026-05-03

### Añadido

- **Ajustes de impresión también en la pantalla Imprimir** (no solo
  en la edición de plantilla). Sección colapsable _"Ajustes de impresión
  (avanzado)"_ con los mismos tres controles (tipo de material,
  velocidad, calidad). Permite hacer un override **solo para este
  trabajo** sin tocar los defaults del template.
- Cada **pestaña** de Print guarda su propio override por separado en
  `sessionStorage`, así que dos trabajos abiertos pueden imprimir con
  ajustes distintos.
- `/api/fields/<template>` ahora devuelve `print_settings` además de
  `fields`. La pantalla de impresión los precarga al cambiar de
  plantilla, así el usuario ve qué ajustes salen por defecto.

### Cambiado

- **"Edit fields" → "Editar plantilla"** (`Edit` en el listado, _"Editar
  plantilla"_ como título de la página). El nombre anterior sugería que
  solo se editaban campos, pero ahora la pantalla cubre también los
  ajustes de impresión genéricos del template.
- **Reordenación de la página Editar plantilla**: los _Ajustes de
  impresión_ (genéricos) van arriba; los _Campos del formulario_
  (específicos) debajo.
- El bloque "Editar código ZPL" ahora vive como botón en la cabecera
  de Ajustes de impresión, no en la cabecera de los campos.

## [0.5.0] - 2026-05-03

### Añadido

- **Pestañas en la pantalla Imprimir.** Puedes tener varios trabajos
  abiertos en paralelo, cada uno con su plantilla, valores de campos
  y número de copias independientes. La barra de pestañas vive sobre
  el formulario al estilo de un navegador, con `+` para abrir nuevas
  (hasta 12) y `×` para cerrar (siempre queda al menos una). El estado
  se guarda en `sessionStorage`, así que un refresh no pierde tu
  trabajo en curso. Implementado todo en cliente (`static/print-tabs.js`),
  el backend sigue viendo un único formulario al enviar.
- **Ajustes de impresión por plantilla** en _Settings → Templates → Edit
  fields_:
  - **Tipo de material**: Térmica directa / Transferencia térmica (con
    ribbon) / Heredar el de la plantilla. Inyecta `^MTD` / `^MTT` al
    ZPL al imprimir.
  - **Velocidad de impresión** (1-14 ips). Inyecta `^PRn`.
  - **Calidad / temperatura** (0-30). Inyecta `~SDnn`. `-1` = heredar.
  - Se guardan en el sidecar JSON junto a los campos. Si los tres
    quedan en "heredar", la sección se borra del sidecar para no
    ensuciar el archivo.

### Cambiado

- `static/app.js` emite ahora un evento `fields:rendered` en
  `#fieldsContainer` después de re-renderizar los campos al cambiar de
  plantilla. Lo aprovecha `print-tabs.js` para restaurar los valores
  del tab que pasa a estar activo, una vez que los inputs nuevos están
  en el DOM. Cualquier otro módulo que necesite engancharse al ciclo
  puede usar el mismo evento.

## [0.4.1] - 2026-05-03

### Cambiado

- **Persistencia de idioma coherente entre Flask y splash.** Hasta ahora,
  Flask solo leía la cookie `comandante_zebra_lang` y caía a
  `Accept-Language` o español si no la encontraba. El splash sí leía
  `~/.comandante_zebra/lang.txt` (que se escribía al cambiar el idioma),
  pero Flask lo ignoraba — si borrabas cookies, perdías la elección.
- Nueva cadena de resolución del idioma activo:
  **cookie → `lang.txt` → `Accept-Language` → español por defecto.**
  Si limpias cookies o cambias de navegador, la app recuerda el último
  idioma elegido. Si nunca lo has cambiado, intenta el del SO. Si no
  coincide con ninguno soportado, español.

## [0.4.0] - 2026-05-02

Renombrado de **Doctor Zebra → Comandante Zebra** como homenaje al
**Norton Commander** de los 80/90 (el icónico file manager de DOS con
su TUI azul cobalto de dos paneles).

### Cambiado

- **Marca**: nombre del proyecto, `.exe` (`ComandanteZebra.exe`), bundle
  identifier macOS (`com.comandantezebra.app`), título de la ventana,
  splash, sidebar, todos los `<title>`/topbar de las plantillas y los
  catálogos i18n EN/ES/CA.
- **Icono / logo**: nueva paleta **azul Norton Commander** (`#0000AA`,
  el clásico DOS blue) con etiqueta blanca centrada y barras zebra en
  lugar de la cruz médica roja anterior. Regenerado `static/icon.png`,
  `icon.ico`, `icon.icns` y `logo.svg`.
- **Cookie de idioma** renombrada a `comandante_zebra_lang`. Cookies
  antiguas con el nombre `doctor_zebra_lang` simplemente caen en desuso
  y se vuelve a evaluar el idioma con `Accept-Language` / locale.
- **Directorio de datos** del usuario renombrado a `~/.comandante_zebra/`.
  La migración suave existente desde `~/.zebra_labels/` sigue siendo
  válida y cubre también el paso intermedio por `~/.doctor_zebra/` si
  alguna instalación quedó ahí (se renombrará en el primer arranque).
- **Repo en GitHub** renombrado a `comandante_zebra`. URLs antiguas
  redirigen automáticamente, pero el remote local debe actualizarse:
  `git remote set-url origin https://github.com/fcopuerto/comandante_zebra.git`.

### Cambiado (DX)

- **Gestión de dependencias migrada a [uv](https://docs.astral.sh/uv/).**
  Nuevo `pyproject.toml` con extras opcionales (`mssql-pure`, `mssql-odbc`)
  y un grupo `build` para PyInstaller, más `uv.lock` para reproducibilidad
  exacta. El workflow de Windows usa `astral-sh/setup-uv` con cache, lo
  que reduce el tiempo de instalación de dependencias de ~50 s a un par
  de segundos en runs sucesivos. Los `requirements*.txt` se mantienen
  como compat para quien prefiera pip clásico.

## [0.3.3] - 2026-05-02

### Cambiado

- **Splash con teatro al estilo años 90**: 8 mensajes de carga rotando
  con barra de progreso animada (de 0 a 100% en ~6 segundos), traducidos
  en EN/ES/CA. Mensajes inventados pero con personalidad: _"Buscando
  impresoras Zebra…"_, _"Calibrando rodillos virtuales…"_,
  _"Sincronizando caché de artículos…"_, _"Calentando el motor de
  previsualización…"_, etc. — terminan con _"Comandante Zebra a punto."_
- Tiempo total del splash subido a ~6,5 s (antes 1,5 s) para que dé
  tiempo a leer los pasos. La ventana principal sigue arrancando en
  paralelo en background; si Flask termina antes, se queda esperando
  para no truncar la animación.
- El idioma del splash se decide al arrancar leyendo
  `~/.comandante_zebra/lang.txt` (escrito por `/api/lang/<code>` cuando el
  usuario lo cambia) y, si no existe, cae al locale del sistema, y por
  último al default español.

## [0.3.2] - 2026-05-02

### Añadido

- **Pantalla de bienvenida (splash) al arranque** estilo años 90 (WordPerfect /
  Word): ventana sin bordes 480×320 con el logo grande, "Comandante Zebra",
  tagline y versión sobre fondo navy con gradiente. Aparece al instante
  mientras Flask arranca en segundo plano y se queda visible un mínimo de
  1,5 s aunque el servidor esté listo antes — para que el branding registre.
- Cuando Flask responde, se abre la ventana principal de la app y el splash
  se cierra (en este orden, para evitar parpadeos).
- El logo viaja embebido en base64 dentro del HTML del splash, así no
  necesita ningún recurso externo ni el servidor Flask para renderizarse.

## [0.3.1] - 2026-05-02

### Añadido

- Cobertura de traducciones EN/ES/CA ampliada al **formulario de impresión**,
  pestañas de Settings, **hub de Settings**, listado de plantillas, conexiones
  a base de datos, perfiles, y títulos del asistente y de las pantallas de
  edición de plantillas.
- Catálogo crece a 151 claves por idioma, con paridad verificada (los tres
  archivos exponen exactamente las mismas claves).
- Bloque común reutilizable: `common.save / cancel / delete / edit / create`,
  etc., para mantener consistencia entre páginas.

### Pendiente

- Traducir los párrafos descriptivos paso a paso del **wizard** (welcome,
  configuración, prueba, all set) — el título y la entrada en sidebar ya
  están traducidos; los pasos detallados quedan como TODO claro.
- Mensajes flash y errores de servidor (no aparecen en HTML estático sino
  vía `flash()` / `jsonify({'message': ...})`).

## [0.3.0] - 2026-05-02

Soporte multi-idioma — primera oleada (sidebar, topbar, dashboard, historial).

### Añadido

- **i18n** con diccionarios JSON (`i18n/en.json`, `es.json`, `ca.json`).
- Selector de idioma en la topbar (`EN · ES · CA`) con el activo destacado.
- Resolución del idioma: cookie `comandante_zebra_lang` → `Accept-Language` →
  **español por defecto**. Las claves no traducidas caen a inglés y, si
  tampoco existen ahí, se muestra la propia clave para que sean visibles.
- Endpoint `POST /api/lang/<code>` que persiste el idioma en cookie de 1 año.
- Páginas traducidas en esta versión: navegación lateral, topbar, dashboard
  completo (KPIs, paneles, tabla de errores) e historial.

### Pendiente para 0.3.1

- Traducir formulario de impresión, asistente, configuraciones (printers,
  plantillas, conexiones, perfiles) y mensajes de error de servidor.

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
- Workflow de GitHub Actions que construye `ComandanteZebra.exe` en cada push
  a `main` y lo adjunta a un GitHub Release cuando se publica un tag `v*`.

### Notas de migración

- El directorio de datos del usuario se llama ahora `~/.comandante_zebra/`.
  Las instalaciones previas que usaban `~/.zebra_labels/` se renombran
  automáticamente en el primer arranque sin perder datos.

[Unreleased]: https://github.com/fcopuerto/comandante_zebra/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/fcopuerto/comandante_zebra/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/fcopuerto/comandante_zebra/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/fcopuerto/comandante_zebra/releases/tag/v0.1.0
