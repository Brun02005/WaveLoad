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
- [x] Esquema de tags migrado sobre la DB real sin pérdida de datos (2026-09-09)
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
- [x] Repositorio bajo control de versiones
- [~] `requirements.txt` completo; falta verificarlo en un venv limpio de verdad
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

**Motor de Collections**
- **Vocabulario de tags** en `domain/tags.py`: 9 namespaces cerrados, `TagSource`,
  normalización de valores a slug, `Tag` y `TagAssignment`. Módulo puro, 23 tests
- **Esquema migrado sobre la librería real** (2026-09-09): `tags`, `track_tags`,
  `collections`, `collection_layers`, `crates`, `crate_entries` + 8 índices, vía
  `DatabaseManager._migrate_collections_schema`. Aditiva, idempotente, corrida primero
  contra un backup: 784 tracks / 784 assets / 781 análisis intactos, `integrity_check` ok,
  `foreign_key_check` vacío. 21 tests sobre DB temporal
- `db_manager` pasó a ser **perezoso** (`get_db_manager()` + PEP 562) y
  `SqliteTrackRepository` acepta un `DatabaseManager` inyectado: importar
  `infrastructure.database` ya no corre migraciones contra la base real del usuario

**Calidad y repositorio**
- **Repositorio git inicializado** (2026-09-09). Primer commit `62ff75a` con los 118
  archivos de código; `.gitignore` excluye `*.db`, `*.log`, `mp3_downloads/`,
  `waveload_cache.json`, `build/`, `dist/` y `.claude/settings.local.json`. Sin remoto.
- **`requirements.txt` completo**: se agregaron `networkx` (lo importa
  `services/graph_service.py`; estaba solo en `WaveLoad.spec`) y `numpy` (uso directo).
  Verificado que los 9 imports de terceros del árbol tienen su paquete declarado.
- **148 tests pasan** (`pytest`, ~22 s), todos headless sobre servicios sin Qt
  (baseline de la sesión: 104)
- QA E2E en `qa_e2e.py`
- `WaveLoad.spec` de PyInstaller existente, `console=False`, con manejo de logging para
  builds sin consola

### En curso

- Paquete de contexto del proyecto (`ARQUITECTURA.md` + `ESTADO.md`) — esta sesión

### Pendiente

**Motor de Collections**
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

**2. Criterio de rendimiento**
Sin un número de latencia máxima y un tamaño de librería de referencia, no hay forma de
saber si la decisión de no cachear aguanta. Hoy solo hay 784 tracks para medir, contra un
objetivo declarado de 50.000+.

**3. Distribución: alcance de plataformas y condiciones legales**
v1 es distribuible a otros DJs. Eso abre dos cosas nunca discutidas: si macOS entra o no,
y bajo qué términos se distribuye una aplicación que incorpora `yt-dlp` (licencias de las
dependencias, y las condiciones de uso de las plataformas de origen).

**4. ¿Existe "congelar a crate"?**
Convertir el resultado de una smart collection en un crate fijo. No bloquea nada de lo que
viene ahora, pero define si `Crate` necesita una columna que apunte a la collection de
origen — y eso sí es una migración.

### Decididas provisionalmente esta sesión (2026-09-09)

Las cinco están anotadas con su fila en la tabla de la sección 5 de `ARQUITECTURA.md`,
incluida la columna "qué la revertiría". Se tomaron sin consulta, eligiendo la opción más
defendible, y están para revertirse si el uso real las contradice.

| Ex-decisión | Qué se eligió | Por qué en una línea |
|---|---|---|
| 2. Frame ID3 | `TXXX:WAVELOAD_TAGS` | Único destino aditivo: no pisa `GRP1`/`COMM`, que pueden tener contenido del usuario |
| 3. Namespaces | 9 cerrados; el usuario crea valores, no namespaces | Abrirlos después es un botón; cerrarlos después es migrar datos |
| 4. Operadores | 9 ops, 10 campos, sin `in_collection`, temporales sólo sobre columnas que existen | Nada del compilador depende de datos que hoy no están |
| 5. Conflicto manual/automático | Coexisten; el recálculo borra sólo su propia `source` | La PK `(track_id, tag_id, source)` ya lo permite sin costo |
| — | Valores normalizados a slug | Sin eso `Techno`/`techno`/`TECHNO` son tres tags |

---

## 5. Próximos 3 pasos

**1. `TagService` + tags derivados sobre los 781 tracks analizados.**
Servicio puro en `services/` que traduzca BPM, clave Camelot y energía a tags `derived`
(`bpm:120-129`, `key:8a`, `energy:high`), idempotente —re-correrlo no duplica y borra sólo
filas `derived`— con tests headless sobre una DB temporal, y después una corrida real
sobre la librería con backup previo.

**2. AST: definición, validación y serialización.**
`services/query_ast.py`: los 9 operadores de la sección 4.4 de `ARQUITECTURA.md`, parseo
desde JSON con errores entendibles, y round-trip. Sin SQL todavía.

**3. Compilador de AST a SQL + evaluador de una capa `filter`.**
Fragmentos parametrizados (nunca interpolados), encadenados como CTEs. Validar de punta a
punta contra los 784 tracks reales y tomar la primera medición honesta de latencia.

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

### 2026-09-09 — unidad 2: decisiones 2/3/4/5 + esquema de Collections migrado
**Hecho:** `domain/tags.py` (vocabulario cerrado de 9 namespaces, `TagSource`,
normalización a slug, `Tag`, `TagAssignment`) y
`DatabaseManager._migrate_collections_schema`, que crea las seis tablas del motor con sus
ocho índices. La migración se corrió **primero contra una copia**
(`waveload_library.premigration-20260909-132020.db`) y se verificó que los conteos de
`tracks` / `track_assets` / `track_analysis` no cambian, que `integrity_check` da ok y que
`foreign_key_check` vuelve vacío, antes de dejarla correr sobre la base real. 44 tests
nuevos; suite total 148/148 en verde.
**Decidido:** las decisiones 2, 3, 4 y 5 de la lista de abiertas, más la normalización a
slug (ver la tabla de la sección 4 y las filas nuevas en la sección 5 de
`ARQUITECTURA.md`). Todas provisionales.
**Efecto colateral resuelto:** `infrastructure.database` construía el `DatabaseManager`
global al importarse, así que cualquier import corría migraciones contra la librería real
del usuario. Ahora es perezoso (`get_db_manager()`) y `SqliteTrackRepository` acepta uno
inyectado, que es lo que permite testear el esquema sobre una DB temporal.
**Bloqueado en:** nada.
**Siguiente:** `TagService` y los tags derivados de los 781 tracks analizados.

**Secciones de `ARQUITECTURA.md` que cambiaron en esta unidad:** 4.1 (namespaces), 4.2
(política de conflicto), 4.4 (lista cerrada de operadores y campos), 4.6 (nombres de tabla
congelados), 4.7 (frame ID3 y lectura), y 5 (siete filas nuevas en la tabla de
decisiones).
