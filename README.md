# 🦓 Doctor Zebra

Imprime etiquetas en impresoras Zebra desde una app de escritorio **Flask + pywebview**:
plantillas ZPL editables, caché offline de lookups y perfiles independientes.

---

## ✨ Características

| Función | Descripción |
|---|---|
| 🖨️ **Impresión ZPL** | Envía ZPL a cualquier impresora Zebra vía TCP (puerto 9100 por defecto) |
| 📄 **Plantillas editables** | Editor ZPL con resaltado oscuro, detección de variables en tiempo real y referencia rápida |
| 👤 **Perfiles independientes** | Cada perfil almacena configuración de impresora, plantilla y campos del formulario |
| 🗄️ **Caché offline** | Tablas de datos (productos, clientes…) almacenadas en SQLite; autocompletado y relleno automático sin red |
| 🖥️ **Ventana nativa** | Usa `pywebview` para abrir una ventana de escritorio; también funciona como servidor Flask estándar |

---

## 🚀 Inicio rápido

```bash
# 1. Clonar e instalar dependencias
git clone https://github.com/fcopuerto/doctor-zebra.git
cd doctor-zebra
pip install -r requirements.txt

# 2a. Ejecutar como app de escritorio (requiere pywebview)
python app.py

# 2b. Ejecutar como servidor web
flask --app app run
# Abrir http://127.0.0.1:5000
```

---

## 📁 Estructura del proyecto

```
doctor-zebra/
├── app.py                     # Rutas Flask + entrada pywebview
├── config.py                  # Rutas y constantes de configuración
├── requirements.txt
├── modules/
│   ├── printer.py             # Envío ZPL por TCP + render de variables
│   ├── profiles.py            # CRUD de perfiles (JSON)
│   ├── zpl_templates.py       # CRUD de plantillas ZPL
│   └── cache.py               # Caché offline SQLite de lookups
├── templates/                 # Plantillas Jinja2
│   ├── base.html
│   ├── index.html             # Formulario de impresión
│   ├── profiles/
│   ├── zpl_templates/
│   └── cache/
├── static/
│   ├── css/style.css
│   ├── js/app.js              # Autocompletado + modal de búsqueda
│   └── vendor/                # Bootstrap 5 + Bootstrap Icons (offline)
├── data/
│   ├── profiles/              # Perfiles en JSON
│   ├── zpl_templates/         # Plantillas .zpl
│   └── cache.db               # Base de datos SQLite (auto-creada)
└── tests/                     # 71 tests con pytest
```

---

## 🧪 Tests

```bash
pytest tests/ -v
```

---

## 🔧 Perfiles

Un **perfil** es un fichero JSON en `data/profiles/` que agrupa:

- **Impresora**: host/IP y puerto TCP
- **Plantilla**: nombre de la plantilla `.zpl` a usar
- **Campos**: definición del formulario (tipo, label, lookup, autofill…)

```json
{
  "name": "Etiquetas almacén",
  "printer": { "host": "192.168.1.100", "port": 9100 },
  "template": "etiqueta_producto",
  "fields": [
    {
      "name": "codigo",
      "label": "Código",
      "type": "text",
      "required": true,
      "lookup": "productos",
      "lookup_value_field": "code",
      "lookup_label_field": "name",
      "autofill": [{"from": "name", "to": "nombre"}]
    }
  ]
}
```

---

## 📄 Plantillas ZPL

Las plantillas se guardan como ficheros `.zpl` en `data/zpl_templates/`.
Las variables usan la sintaxis `{nombre_variable}`:

```zpl
^XA
^FO40,30^A0N,28,28^FD{nombre}^FS
^FO40,65^A0N,20,20^FDCod: {codigo}^FS
^FO40,100^BY2^BCN,80,Y,N,N^FD{codigo}^FS
^XZ
```

---

## 🗄️ Caché offline

Un **lookup** es un array JSON (ej. catálogo de productos) almacenado en SQLite.
Se puede importar desde una URL HTTP y actualizar con un clic.
Cuando la app funciona sin red, los datos ya están disponibles para autocompletar.

```
GET /api/lookup/{name}/search?q=texto   → resultados filtrados (máx. 50)
```
