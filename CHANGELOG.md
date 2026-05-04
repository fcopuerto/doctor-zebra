# Changelog

Todos los cambios relevantes de Comandante Zebra se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado adopta [Semantic Versioning](https://semver.org/lang/es/).

## [Unreleased]

## [0.13.1] - 2026-05-05

### Añadido

- **Añadir peers manualmente por IP** — fallback cuando mDNS no
  funciona (wifi de invitado, AP isolation, redes con multicast
  bloqueado). Nuevo formulario en _Configuración → Red_: introduces
  IP + puerto del otro equipo, la app le hace `GET /api/peer/info`
  para verificar que responde, y si todo va bien lo añade. Los peers
  manuales se muestran en la lista con badge `· manual` y un botón ×
  para quitarlos. Se persisten en `network.json`.
- Endpoints nuevos:
  - `POST /api/network/peers/manual` `{address, port}` — probe + add.
  - `DELETE /api/network/peers/manual` `{address, port}`.
- `/api/network/peers` fusiona descubiertos por mDNS + manuales (sin
  duplicar si una IP coincide).

### Arreglado

- **Pestaña nueva ya no hereda los valores de la anterior.** Pulsar
  `+` en la barra de pestañas crea una pestaña limpia: los inputs se
  resetean en lugar de quedar mostrando lo del trabajo anterior. Si
  quieres clonar el trabajo actual, próximamente habrá un botón
  _Duplicar pestaña_ explícito.
- **El badge "actualización disponible" ya no avisa eternamente** tras
  haber actualizado la app. El cache del updater detecta cuando
  `__version__` ha cambiado desde la última comprobación y fuerza un
  refresh, así que la primera apertura tras instalar una versión
  nueva ya muestra el estado real (sin esperar 24 h al TTL).

### Cambiado (rendimiento)

- **Cache de `printer_status`** con TTL de 5 s. La consulta a
  `lpstat`/`winspool` cuesta 50-300 ms y se hacía en cada render del
  sidebar. Cacheada queda en ~0 ms para requests sucesivos. La app
  se nota mucho más fluida después del splash.
- **Más rutas en el warmup paralelo** durante el splash: incluye
  ahora `/history`, `/config` y todas sus subpáginas, `/config/tools`
  y `/setup`. Así Jinja compila todas las plantillas mientras el
  splash sigue en pantalla y el primer click en cualquier tab es
  instantáneo, no solo en las que ya estaban en el warmup.

## [0.13.0] - 2026-05-05

### Añadido

- **Tres modos visuales para comparar versiones** en la sección
  Historial de Editar plantilla. Toolbar con botones tipo pestaña:
  - **Lado a lado**: las dos imágenes una al lado de la otra (lo
    que ya había).
  - **Slider**: superpuestas, con un slider de 0–100 que controla la
    opacidad de la imagen B → puedes hacer crossfade y ver
    exactamente qué se mueve.
  - **Diff visual**: superpuestas con `mix-blend-mode: difference`.
    Las zonas iguales salen negras, las diferencias se iluminan —
    detecta al instante elementos movidos, redimensionados o
    nuevos sin tener que comparar pixel a pixel a ojo.
- Mejor feedback en **Settings → Tools**: el endpoint `/api/tools/run`
  ahora devuelve `target`, `backend` y `bytes` enviados, y el toast
  de la UI los muestra. Si la impresora ignora el comando, el mensaje
  recuerda revisar la cola de impresión y el modo (ZPL vs EPL).
  El log ahora registra el ZPL exacto enviado (nivel INFO).

### Cambiado

- **Splash de vuelta a 7 s** (de 4.5 s) — sirve también como branding
  visible. El warmup paralelo en background sigue activo, así que es
  tiempo "gratis" sin penalizar la app.

## [0.12.1] - 2026-05-05

### Cambiado

- **Warmup en paralelo durante el splash.** En cuanto Flask responde,
  `desktop.py` lanza GETs en threads daemon (uno por endpoint) a las
  rutas que el usuario suele tocar primero: `/healthz`, `/`,
  `/dashboard`, `/api/network/diagnostics` y `/api/update/check`. Como
  son threads paralelos, el más lento (típicamente la consulta a
  GitHub para el update check) no bloquea al resto. Cuando el splash
  termina, las pantallas principales ya están "calientes" — el primer
  click cuesta menos.
- **Splash más corto**: `SPLASH_MIN_MS` baja de 6.5 s a 4.5 s. Con el
  warmup paralelo no hace falta tanto tiempo en pantalla; el intervalo
  entre los 8 pasos de carga se ajusta automáticamente.

## [0.12.0] - 2026-05-05

### Añadido

- **Contador de versiones** visible en la cabecera de _Form Fields_:
  un badge clickable tipo `📜 5 versiones guardadas` que enlaza con
  scroll a la sección Historial. De un vistazo sabes cuánto has
  iterado un template.
- **Comparación visual con preview lado-a-lado.** Cuando comparas dos
  refs, además del diff del ZPL ves **dos imágenes renderizadas**
  (vía Labelary) una al lado de la otra, con su etiqueta de versión
  encima:

      ┌───── v3 (2026-05-04) ─────┬───── current ─────┐
      │  [imagen renderizada]     │  [imagen]          │
      └────────────────────────────┴────────────────────┘
      ────── unified diff debajo ──────

  Así puedes ver el cambio "de verdad" — qué se mueve, qué crece, qué
  desaparece — no solo el diff de coordenadas en hex.
- Endpoint nuevo `GET /api/templates/<n>/preview?ref=current|<ts>`
  que renderiza el ZPL de la ref como PNG (placeholders vacíos para
  inspección de diseño) y devuelve `image/png` directo, ideal para
  meter en un `<img src=...>` sin escribir a disco.

## [0.11.1] - 2026-05-04

### Cambiado

- **Versionado integrado en la página _Editar plantilla_** en vez de
  escondido en un modal. Nueva tarjeta **"Historial de versiones"**
  visible debajo de los campos del formulario, con:
  - **Lista de versiones expandible**: click en una fila → muestra el
    ZPL de esa versión inline (no abre nada nuevo).
  - **Selector de comparación con dos dropdowns** (`A: [v3 ▾]  vs  B:
    [current ▾]`) más botón Comparar → diff inline justo debajo, con
    `+`/`-`/`@@` coloreados.
  - **Botones por fila**: _vs current_ (compara directamente con el
    archivo vivo) y _Restaurar_.
  - El botón "Versiones" del breadcrumb ahora hace **scroll** a la
    tarjeta en lugar de abrir un diálogo.
- Modal `<dialog>` de versiones eliminado — toda la funcionalidad vive
  ya en la página, sin overlays.

## [0.11.0] - 2026-05-04

### Añadido

- **Números de versión secuenciales** (v1, v2, v3…) además del
  timestamp. Se calculan al snapshotear y se guardan en `meta.json`.
  Los snapshots viejos sin número se infieren del orden cronológico.
- **Comparar dos versiones** con diff unificado:
  - Endpoint `GET /api/templates/<name>/versions/compare?a=…&b=…` que
    acepta timestamps o `current` y devuelve `{a_label, b_label, lines}`
    con el diff en formato unified-diff estándar.
  - En el modal de Versiones: checkbox por fila, botón **Comparar**
    (con dos seleccionadas) y **Comparar con actual** (con una
    seleccionada). El resultado se pinta inline con `+` verde, `-`
    rojo y `@@ … @@` resaltado.
- **Imprimir desde una versión específica:**
  - `GET /api/fields/<template>?version=<ts>` lee los campos del
    sidecar de esa versión.
  - `POST /generate` acepta `version_ts`. Si no es `current`, usa el
    ZPL del snapshot y los campos del sidecar de esa versión.
  - Nuevo selector **Versión** en la pantalla _Imprimir_, al lado de
    Plantilla. Al cambiar de versión, el formulario se reconstruye
    con los campos correspondientes a esa versión.
  - Cada **pestaña** de impresión guarda su propia versión elegida en
    `sessionStorage`, así que dos tabs pueden imprimir el mismo
    template en versiones distintas a la vez.
- `zpl.render_text(zpl, fields)` para renderizar ZPL ya cargado en
  memoria (necesario para imprimir desde snapshots sin tocar el
  archivo vivo).

## [0.10.0] - 2026-05-04

### Añadido

- **Versionado de plantillas con restore.** Cada vez que guardas un
  cambio en una plantilla (campos, ajustes de impresión o el ZPL en
  bruto), la app **automáticamente snapshotea el estado anterior** a
  `<perfil>/templates_zpl/.versions/<plantilla>/<timestamp>/` antes de
  escribir nada.
- Botón **"Versiones"** en la cabecera de la página _Editar plantilla_
  (Settings → Plantillas → Editar). Abre un modal con la lista de
  snapshots ordenados del más reciente al más antiguo, mostrando
  fecha/hora UTC, tamaño, si tenía sidecar de campos asociado y el
  motivo del snapshot (`edit`, `zpl_edit`, `restore`).
- Botón **"Ver"** por versión → muestra el ZPL guardado en la propia
  modal para que puedas confirmar antes de restaurar.
- Botón **"Restaurar esta versión"** con confirmación. **Antes de
  pisar el archivo actual, lo snapshotea** con motivo `restore`, así
  que también puedes deshacer un restore si te equivocas.
- Endpoints nuevos:
  - `GET  /api/templates/<name>/versions`
  - `GET  /api/templates/<name>/versions/<ts>`
  - `POST /api/templates/<name>/versions/<ts>/restore`
- Nuevo módulo `zebra/template_history.py` con la lógica de snapshot,
  list, get y restore. La carpeta `.versions/` es oculta para que no
  ensucie el explorador de plantillas.

## [0.9.0] - 2026-05-04

### Añadido

- **Pestaña Herramientas** en Configuración. Botones de un solo clic
  que disparan comandos ZPL administrativos contra la impresora por
  defecto, agrupados por categoría:

  | Grupo | Tools |
  |---|---|
  | Diagnóstico | Print Configuration Label (`~WC`), Print Sensor Profile (`~JG`), Print Network Config (`~WL`) |
  | Calibración | Calibrar Sensor de Papel (`~JC` + `^JUS`), Detectar Longitud de Etiqueta (`~JL`) |
  | Mantenimiento | Form Feed (`^XA^XZ`), Guardar Ajustes en Flash (`^JUS`), Reiniciar Impresora (`~JR`, con confirmación) |
  | Test | Imprimir Etiqueta de Prueba |

  Cada tarjeta enseña el comando ZPL real para que se vea qué se está
  enviando.
- Endpoint nuevo `POST /api/tools/run` con body `{ tool_id, target? }`.
  Si `target` no se especifica usa la impresora por defecto del perfil.
- Nuevo módulo `zebra/printer_tools.py` con el catálogo de tools (id,
  grupo, ZPL, icono, flag de confirmación). Sumar tools nuevas es
  añadir una entrada al diccionario.
- Icono `i-wrench` en el sprite SVG para la nueva pestaña.

## [0.8.0] - 2026-05-04

### Añadido

- **Notificación de actualizaciones disponibles.** La app consulta
  `api.github.com/repos/fcopuerto/comandante_zebra/releases/latest`
  cada 24 h (caché en `~/.comandante_zebra/update.json` para no
  saturar la API). Si hay una versión más nueva, aparece un **badge
  dorado pulsante** _"→ vX.Y.Z"_ en el footer del sidebar.
- Click en el badge → modal con tu versión, la última, fecha de
  publicación y notas del release. Botón **"Descargar"** que abre el
  Release en el navegador.
- Botón **"Saltar esta versión"** que silencia el badge hasta que
  aparezca otra versión más nueva (persistido en `update.json`).
- Endpoints nuevos: `GET /api/update/check`, `POST /api/update/dismiss`.
- Sin descarga ni reemplazo automático del `.exe` — ese es el F2 que
  requiere matar el proceso, sustituir el binario en uso, relanzar y
  manejar errores. Se queda como ampliación futura si hace falta; F1
  cubre el 95% del valor con cero riesgo.

## [0.7.5] - 2026-05-03

### Añadido

- **Galones de comandante en el icono.** Tres chevrons dorados (estilo
  rango militar) sobre el barcode/zebra del logo. La paleta queda:
  fondo azul Norton Commander, etiqueta blanca, barras navy y galones
  dorados (#C9A227) que cuentan claramente que es el "Comandante".
  Regenerado `static/icon.png`, `icon.ico`, `icon.icns` y `logo.svg`.
- **Apertura automática del firewall de Windows para mDNS.** Nuevo
  módulo `zebra/firewall.py` con un helper que lanza PowerShell con
  elevación UAC y crea (o refresca) reglas de entrada y salida en UDP
  5353 con el nombre _"Comandante Zebra (mDNS)"_.
- Endpoint `POST /api/network/firewall/open` (Windows-only — devuelve
  400 + instrucciones manuales en otros sistemas).
- Sección **Firewall** dentro del card de Diagnóstico en _Settings →
  Red_:
  - En Windows: botón **"Abrir firewall para mDNS"** que dispara el
    helper elevado.
  - En macOS: nota informativa de que no hace falta nada.
  - En Linux: snippet copiable con los comandos para UFW, firewalld
    e iptables.
- Diagnostics endpoint amplía su payload con `firewall: { os, manual_instructions }`.

## [0.7.4] - 2026-05-03

### Arreglado (CI)

- Si SignPath falla por cualquier motivo (config en el panel, API caída,
  timeout) el workflow **ya no aborta el job**: marcado el step con
  `continue-on-error: true`. El SHA-256, VirusTotal, upload y release
  vuelven a correr siempre, así que como mínimo se publica el `.exe`
  sin firmar (con la nota `⚠️ No firmado` en las release notes) en
  vez de no publicar nada.

## [0.7.3] - 2026-05-03

### Arreglado (CI)

- El job ahora se ata al GitHub environment `copilot`, donde viven
  realmente los secrets `SIGNPATH_API_TOKEN` y `VIRUSTOTAL_API_KEY`.
  Estaban configurados ahí (auto-creado por GitHub Copilot) en vez de
  a nivel de repo, así que en 0.7.2 aún se saltaban los steps. Con
  esto, la firma y el scan de VT ya deberían ejecutarse en el siguiente
  build/tag.

## [0.7.2] - 2026-05-03

### Arreglado (CI)

- En 0.7.1 los steps de SignPath y VirusTotal aparecían como
  **skipped** aunque los secrets estaban configurados en el repo. La
  causa: el `env:` declarado en cada step **no** está disponible en su
  propio `if:` (gotcha clásico de GitHub Actions). Movidos
  `SIGNPATH_API_TOKEN` y `VIRUSTOTAL_API_KEY` a `env:` a nivel de
  **job**, así sí los ve el `if:`. A partir de esta versión, si los
  secrets están configurados, el `.exe` sale firmado y el scan de VT
  aparece en las release notes.

## [0.7.1] - 2026-05-03

Release puramente de distribución: la aplicación es idéntica a 0.7.0,
pero el `.exe` ahora puede salir **firmado** (vía SignPath.io Foundation)
y cada build adjunta el enlace al **escaneo de VirusTotal** en las
release notes.

### Cambiado (CI)

- **Code signing con SignPath.io Foundation** integrado en el workflow.
  Se activa solo si el repo tiene configurado el secret
  `SIGNPATH_API_TOKEN`. Cuando está, tras el build:
  1. Sube el `.exe` sin firmar como artifact temporal.
  2. SignPath descarga el binario, lo firma con el certificado OV de
     SignPath Foundation y devuelve el firmado.
  3. El firmado sustituye al unsigned en `dist/` antes de SHA-256 y
     VirusTotal, así toda la integridad publicada corresponde al
     binario firmado.
  4. Las release notes indican si la build salió firmada o no.

  Project slug (`COMANDANTE_ZEBRA`), signing policy slug
  (`release_policy`) y organization ID están hardcodeados en el
  workflow; lo único que necesita el repo es el secret del token de
  API. Si SignPath falla o el secret no está, la build sigue y publica
  el `.exe` sin firmar.

- **Scan de VirusTotal automático** en cada build de Windows. Es
  opcional: solo se ejecuta si el repo tiene el secret
  `VIRUSTOTAL_API_KEY`. Cuando está, sube el `.exe`, espera el análisis
  y publica el enlace en las release notes (junto al SHA-256). Útil
  como visibilidad rápida de si algún AV marca falsos positivos, y los
  resultados de VT se comparten con muchos vendors AV (Microsoft
  incluido), por lo que indirectamente ayuda a reducir warnings de
  SmartScreen sin tener que enviar manualmente.
- README añade sección **CI / mantenimiento** con instrucciones para
  activar el secret de VirusTotal y para aplicar a SignPath.io
  Foundation (firma de código gratis para open source — sustituiría
  todas las mitigaciones de SmartScreen actuales).

## [0.7.0] - 2026-05-03

Pulido general — diagnóstico de red, healthz, traducción del wizard
y refuerzos de seguridad en el peer endpoint.

### Añadido

- **Diagnóstico de red** en Configuración → Red. Nueva sección que
  muestra en vivo si zeroconf está disponible, si estamos escuchando,
  si nos estamos anunciando, qué IP de LAN tenemos y cuántos peers
  hemos visto. Cuando algo no va, muestra **consejos concretos**
  traducidos en EN/ES/CA: firewall en Windows bloqueando UDP/5353,
  Bonjour service no instalado, otra instancia en subred distinta,
  zeroconf no instalado, etc. Endpoint nuevo `/api/network/diagnostics`.
- **Endpoint `/healthz`** que devuelve `{ ok, version, profile, uptime_s }`.
  Útil para que el splash sepa cuándo Flask responde y para integraciones
  externas de monitorización.
- **Wizard traducido al castellano y catalán** — todos los pasos,
  hints, botones, opciones (USB / red / avanzado), revisión final.
  Cierra el TODO que arrastrábamos desde 0.3.1.
- **Sección Red en el README** con cómo funciona el descubrimiento,
  PIN, qué se comparte y troubleshooting de firewall/Bonjour.

### Cambiado

- `discovery.py` captura el último error de init y de publish y los
  expone en `diagnostics()` para que la UI pueda decir "tu firewall
  está bloqueando 5353/UDP" en lugar de un genérico "no peers".

### Seguridad

- `pull_templates` rechaza nombres con `/`, `\` o `..` y exige sufijo
  `.zpl`, así un peer malicioso no puede inducirnos a escribir fuera
  del directorio de templates.
- `peer_get_template` rechaza el mismo patrón antes de tocar disco
  (la whitelist de templates ya era la defensa real, esto es solo
  para fallar pronto).

### Arreglado

- Catálogos i18n crecen a 265 claves alineadas en EN/ES/CA.

## [0.6.1] - 2026-05-03

### Arreglado

- `python desktop.py` reventaba con `NameError: ServiceListener is not
  defined` cuando `zeroconf` no estaba instalado en el entorno de Python
  activo (típico al correr desde una venv distinta de la `.venv` de uv).
  Ahora el módulo `discovery` degrada limpiamente: si `zeroconf` no se
  importa, la app sigue arrancando, la pantalla **Red** muestra una lista
  de peers vacía y el announcement no se publica.

### Cambiado (Windows / SmartScreen)

- **UPX desactivado** en `build_desktop.spec`. El bootloader comprimido
  con UPX comparte huella con muchos binarios PyInstaller-malware
  antiguos y disparaba SmartScreen / Defender. El `.exe` resultante es
  algo más grande pero entra mucho más limpio.
- **SHA-256** del `.exe` calculado en CI y publicado como
  `ComandanteZebra.exe.sha256` junto al binario en cada Release y como
  artifact del workflow. Permite verificar que descargaste exactamente
  los bytes que construyó el CI sin necesidad de un certificado pagado.
- README añade una sección sobre el aviso de SmartScreen y cómo
  comprobar el SHA-256 con `Get-FileHash` en PowerShell.

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

[Unreleased]: https://github.com/fcopuerto/comandante_zebra/compare/v0.13.1...HEAD
[0.13.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.13.0...v0.13.1
[0.13.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.12.1...v0.13.0
[0.12.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.11.1...v0.12.0
[0.11.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.7.5...v0.8.0
[0.7.5]: https://github.com/fcopuerto/comandante_zebra/compare/v0.7.4...v0.7.5
[0.7.4]: https://github.com/fcopuerto/comandante_zebra/compare/v0.7.3...v0.7.4
[0.7.3]: https://github.com/fcopuerto/comandante_zebra/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/fcopuerto/comandante_zebra/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/fcopuerto/comandante_zebra/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/fcopuerto/comandante_zebra/compare/v0.6.0...v0.6.1
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
