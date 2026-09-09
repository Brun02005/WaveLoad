# WaveLoad — Estado

> Documento vivo. Se actualiza en cada sesión de trabajo. Las decisiones estables viven en
> `ARQUITECTURA.md` y no se repiten acá.
>
> Convención: `[PENDIENTE: x]` marca algo que todavía no está decidido.

---

## 1. Snapshot

**Fecha:** 2026-09-09

**Dónde está el proyecto:** la infraestructura core está congelada y funcionando
(sprints 1 a 4.4.1 cerrados). El pipeline completo de descarga → conversión →
etiquetado → librería → análisis → grafo → set → export está construido y probado:
104 tests pasan, la librería real tiene 784 tracks con 781 analizados.

**En qué estoy trabajando ahora:** en el arranque del motor de Collections. El modelo
quedó elegido (tags/queries por capas) después de descartar grafos, smart albums, canvas
espacial y línea de tiempo. El proyecto ya está bajo git (primer commit `62ff75a`). El
botón "Colecciones" sigue deliberadamente oculto en `ui/shell/sidebar.py` para no dejar un
callejón sin salida en la navegación.

---

## 2. Definición de "v1 terminado" — PROPUESTA

> Esta checklist **es una propuesta**, no algo que haya sido decidido antes. Revisala y
> cerrala; hasta entonces, v1 no tiene un límite acordado.

v1 es distribuible a otros DJs, no solo de uso personal. Eso agrega requisitos de
empaquetado y de primer arranque que no existirían en una herramienta privada.

**Motor de Collections**
- [ ] Esquema de tags migrado sobre la DB real sin pérdida de datos
- [ ] Tagging manual: asignar y quitar tags a un track y a una selección múltiple
- [ ] Tags derivados: BPM, clave y energía generan tags automáticamente para los 781
      tracks ya analizados, y para cada track nuevo al analizarse
- [ ] Tags heredados: `source_platform` y `source_playlist_name` se convierten en tags al
      importar o descargar
- [ ] Tags por IA: clasificación de género/mood funcionando end-to-end
- [ ] Builder de capas: crear, reordenar, activar/desactivar y borrar capas de una
      SmartCollection, con el conteo de resultados visible por capa
- [ ] Evaluación compilada a SQL, con AST persistido y versionado
- [ ] Crates manuales: crear, agregar tracks, reordenar, borrar
- [ ] Escritura de tags al ID3

**Integración**
- [ ] El workspace "Colecciones" es visible en el sidebar y funciona
- [ ] Desde una collection se puede generar el grafo
- [ ] Desde una collection se puede generar un set
- [ ] Desde una collection se puede exportar a M3U8 y XML de Rekordbox

**Calidad y distribución**
- [ ] Repositorio bajo control de versiones
- [ ] `requirements.txt` completo y verificado en un entorno limpio
- [ ] Suite de tests en verde, con cobertura del motor de queries
- [ ] Primer arranque limpio: librería vacía, sin errores, con un camino obvio a la
      primera descarga o import
- [ ] Los errores se muestran como mensajes entendibles, no como trazas
- [ ] Instalador `.exe` que corre en una máquina sin Python ni FFmpeg preinstalados
- [ ] `[PENDIENTE: definir el criterio de rendimiento — qué latencia máxima de evaluación
      es aceptable y sobre qué tamaño de librería se mide]`

**No entra en v1:** ver la sección 7 de `ARQUITECTURA.md`.

---

## 3. Hecho / En curso / Pendiente

### Hecho

**Core y descarga**
- Pipeline asíncrono de descarga con `yt-dlp`, máquina de estados con transiciones
  validadas (`core/state_machine.py`), reintentos y recuperación ante fallos
- `SettingsService` centralizado como única fuente de verdad de configuración
- Event bus con `TrackDownloadedEvent` / `TrackCreatedEvent`
- Sanitización única de rutas (`build_final_mp3_path`) y prevención de duplicados
- Resolución de streams, cookies de navegador, resolver de Spotify para metadata

**Librería y datos**
- Esquema SQLite con migraciones idempotentes y transaccionales que corren en cada
  arranque; deduplicación de assets e índice UNIQUE sobre `track_assets.file_path`
- Columnas `source_*` ya presentes y pobladas
- Repositorio con inyección de dependencias (`SqliteTrackRepository`)
- Pipeline de importación de archivos locales con diálogos de selección y progreso
- Metadata + ID3 + carátulas embebidas; limpieza de nombres de archivo
- **784 tracks reales en la librería**

**Análisis y musicología**
- BPM, clave en notación Camelot (perfiles Shaath) y energía 1–10, con librosa
- **781 de 784 tracks analizados**
- Motor de compatibilidad armónica completo (rueda Camelot, ventana ±12% de BPM)
- `SimilarityEngine` con pesos configurables y renormalización
- Grafo de conocimiento con NetworkX: k-NN top-6, umbral 70, layout estable entre builds,
  comunidades, path finder
- `SetBuilderService`: greedy + 2-opt sobre curvas de energía por tipo de evento
- Export a M3U8 extendido y a XML de Rekordbox

**UI**
- Shell de 5 zonas (`AppShell`: toolbar, sidebar, workspace, context panel, bottom
  workspace) con splitters
- Design system modular en `ui/theme/` (colores, spacing, tipografía, iconos)
- Workspaces: Descargas, Librería, Grafo, Ajustes
- `LibraryWorkspace` desacoplado vía `LibraryService`

**Calidad y repositorio**
- **Repositorio git inicializado** (2026-09-09). Primer commit `62ff75a` con los 118
  archivos de código; `.gitignore` excluye `*.db`, `*.log`, `mp3_downloads/`,
  `waveload_cache.json`, `build/`, `dist/` y `.claude/settings.local.json`. Sin remoto.
- **`requirements.txt` completo**: se agregaron `networkx` (lo importa
  `services/graph_service.py`; estaba solo en `WaveLoad.spec`) y `numpy` (uso directo).
  Verificado que los 9 imports de terceros del árbol tienen su paquete declarado.
- 104 tests pasan (`pytest`, ~20 s), todos headless sobre servicios sin Qt
- QA E2E en `qa_e2e.py`
- `WaveLoad.spec` de PyInstaller existente, `console=False`, con manejo de logging para
  builds sin consola

### En curso

- Paquete de contexto del proyecto (`ARQUITECTURA.md` + `ESTADO.md`) — esta sesión

### Pendiente

**Motor de Collections — nada construido**
- Esquema y migración de `tags` / `track_tags` / `collections` / `collection_layers` /
  `crates` / `crate_entries`
- Definición del AST y su serialización
- Compilador de AST a SQL parametrizado
- Evaluador de la pila de capas (fold con `filter` / `exclude` / `union`)
- Servicio de tagging (manual, derivado, heredado)
- Tagging por IA — no existe nada: `track_embeddings` tiene 0 filas y no hay modelo
  integrado
- Escritura de tags al ID3
- `CollectionsWorkspace` completo y su entrada en el sidebar
- Conexión Collections → grafo / set builder / export

**Deuda técnica identificada**
- `pillow` está declarado en `requirements.txt` y como hidden import en `WaveLoad.spec`,
  pero ningún módulo importa `PIL`. Verificar si el build lo necesita de verdad o si es
  peso muerto en el `.exe`
- Falta verificar `requirements.txt` en un venv limpio de verdad (hoy solo se verificó que
  todo import de terceros tiene paquete declarado, contra el entorno ya instalado)
- `LibraryService.scan_library()` y `check_missing_files()` son stubs que solo loguean
- La barra de búsqueda del toolbar está marcada como stub en el código
- `Track.energy` es `int` (1–10) pero `track_analysis.energy_level` es `REAL`: la
  conversión está implícita y sin verificar
- Hay tres archivos `.db` sueltos en la raíz (`waveload_library.db`, su backup y
  `waveload_library.orphan-backup.db`) sin política de retención
- `waveload_error.log` pesa 4,3 MB sin rotación

---

## 4. Decisiones abiertas

Ordenadas por cuánto bloquean.

**1. IA como fuente de tags en v1 — el mayor riesgo del alcance**
Está dentro de v1 por decisión explícita, pero no hay nada: `track_embeddings` está en 0
y ningún modelo está integrado. Es el único ítem de v1 sin ninguna base construida, y
además es el que empuja el tamaño del `.exe` y el tiempo de primer arranque.
Opciones: (a) integrar un modelo local de clasificación por audio; (b) derivar género de
metadata externa en lugar de audio; (c) sacar la IA de v1 y dejar las otras tres fuentes
de tags, que sí se apoyan en lo ya construido.

**2. A qué frame ID3 se escriben los tags**
Bloquea el diseño del sync. Opciones: TXXX con clave propia (limpio, invisible para otro
software), GRP1 (Rekordbox lo lee como "Grouping", así que los tags aparecen allá sin
importar nada), COMM.

**3. Set inicial de namespaces y si el usuario puede crear namespaces nuevos**
Bloquea el diseño de la UI de tagging y del builder de capas.

**4. Lista cerrada de operadores y campos consultables de v1**
Bloquea la escritura del compilador a SQL. En particular: si una capa puede referenciar a
otra collection (`in_collection`), y si hay predicados temporales — estos últimos
requieren columnas que hoy no existen.

**5. Política de conflicto entre tags manuales y automáticos**
No bloquea el esquema (la columna `source` ya cubre el caso), pero sí la UI y el
comportamiento del re-análisis.

**6. Criterio de rendimiento**
Sin un número de latencia máxima y un tamaño de librería de referencia, no hay forma de
saber si la decisión de no cachear aguanta. Hoy solo hay 784 tracks para medir, contra un
objetivo declarado de 50.000+.

**7. Distribución: alcance de plataformas y condiciones legales**
v1 es distribuible a otros DJs. Eso abre dos cosas nunca discutidas: si macOS entra o no,
y bajo qué términos se distribuye una aplicación que incorpora `yt-dlp` (licencias de las
dependencias, y las condiciones de uso de las plataformas de origen).

---

## 5. Próximos 3 pasos

**1. Cerrar las decisiones 2, 3 y 4 y escribir la migración de tags.**
Frame ID3, namespaces iniciales y lista de operadores. Con eso definido, escribir la
migración idempotente que crea `tags`, `track_tags`, `collections`, `collection_layers`,
`crates` y `crate_entries` con sus índices, siguiendo el patrón que ya existe en
`infrastructure/database.py`. Correrla contra un backup antes que contra la base real.

**2. `TagService` + tags derivados sobre los 781 tracks analizados.**
Servicio puro en `services/` que traduzca BPM, clave Camelot y energía a tags `derived`,
idempotente (re-correrlo no duplica), con tests headless sobre una DB temporal.

**3. AST + compilador a SQL + evaluador de una capa `filter`.**
Validar de punta a punta el esquema, el AST y el compilador con datos reales antes de
invertir en UI. Primera medición honesta de rendimiento sobre los 784 tracks.

## 6. Log de handoffs

<!-- Formato sugerido por entrada:
### AAAA-MM-DD
**Hecho:** …
**Decidido:** …
**Bloqueado en:** …
**Siguiente:** …
-->

### 2026-09-09 — unidad 1: git + entorno reproducible
**Hecho:** `git init` en la raíz (sin remoto, no se pushea a ningún lado). `.gitignore`
ampliado para excluir datos del usuario (`*.db`, `mp3_downloads/`, `waveload_cache.json`),
logs y artefactos de build. Primer commit `62ff75a` con 118 archivos. `requirements.txt`
completado con `networkx` y `numpy`. Smoke test de import de los 12 módulos principales +
suite completa: 104/104 en verde.
**Decidido:** no se versionan las `.db` — la librería es dato del usuario, no del
repositorio. Los backups siguen viviendo sueltos en la raíz hasta que haya política de
retención.
**Bloqueado en:** nada.
**Siguiente:** cerrar decisiones 2, 3 y 4 y escribir la migración de tags.
