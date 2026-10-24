# WaveLoad v3

Software de escritorio para DJs: gestor de librería musical con arquitectura por capas (hexagonal / clean architecture). Organiza, cachea y prepara tracks para sets, con foco en un motor de tags/consultas como base a largo plazo.

## Stack

- **Lenguaje:** Python 3
- **UI:** capa `ui/` (aplicación de escritorio)
- **Persistencia:** SQLite (librería local del usuario)
- **Testing:** pytest (unit + e2e)
- **Empaquetado:** PyInstaller (`WaveLoad.spec`)

## Arquitectura

Separación por capas para mantener el dominio independiente de la infraestructura:

```
domain/          Entidades y reglas de negocio
application/     Casos de uso
services/        Servicios de aplicación
infrastructure/  Adaptadores (DB, APIs externas, filesystem)
core/            Utilidades transversales
workers/         Tareas en segundo plano
ui/              Interfaz de escritorio
storage/         Acceso a almacenamiento
tools/           Scripts auxiliares
tests/           Suite de pruebas
```

Documentación de diseño: ver `ARQUITECTURA.md` y `ESTADO.md`.

## Puesta en marcha

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

pip install -r requirements.lock       # versiones exactas con las que pasa la suite
pip install pytest                     # sólo para correr los tests

python main.py
```

`requirements.txt` declara las dependencias directas con su versión mínima;
`requirements.lock` fija el entorno completo. Usá el lock para desarrollar y
para empaquetar: un `pip install` sin versiones fijas trajo en el pasado un
Python sin `librosa` y el análisis falló en silencio.

### Verificación

```bash
python -m pytest -q                          # suite headless (servicios, sin Qt)
python tools/smoke_collections_ui.py         # UI de Colecciones sobre una librería sintética
```

`WAVELOAD_DATA_DIR=<carpeta>` hace que la app use otra carpeta de datos (base,
log, caché): sirve para probar sobre una copia sin tocar la librería real.
`WAVELOAD_DEBUG=1` sube el log a nivel DEBUG.

## Datos del usuario

La librería musical (`*.db`), los logs, dumps y descargas (`mp3_downloads/`) **no se versionan** — son datos locales de cada usuario y están ignorados en `.gitignore`.
