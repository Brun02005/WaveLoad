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
404 tests pasan, la librería real tiene 784 tracks con 781 analizados y **3127 tags
automáticos ya asignados**.

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
- [~] Tags derivados: los 781 tracks analizados ya tienen sus tags de BPM, clave y
      energía (2343 asignaciones). Falta enganchar el recálculo al análisis de un track
      nuevo
- [~] Tags heredados: los 784 tracks ya tienen su tag de plataforma (784 asignaciones;
      ninguno tiene `source_playlist_name` poblado todavía). Falta engancharlo al import y
      a la descarga
- [ ] Tags por IA: clasificación de género/mood funcionando end-to-end
- [~] Builder de capas: la lógica está entera y probada (crear, reordenar,
      activar/desactivar, borrar, y el conteo por capa en una sola consulta); falta la UI
- [~] Evaluación compilada a SQL, con AST versionado; falta persistir las collections
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
- [~] Suite de tests en verde (329), con cobertura del AST y del compilador; falta la
      del evaluador de capas y la de la UI
- [ ] Primer arranque limpio: librería vacía, sin errores, con un camino obvio a la
      primera descarga o import
- [ ] Los errores se muestran como mensajes entendibles, no como trazas
- [ ] Instalador `.exe` que corre en una máquina sin Python ni FFmpeg preinstalados
- [x] Criterio de rendimiento definido y medido: 100 ms la primera página de resultados
      y 1 s el conteo exacto por capa, sobre una librería de 50.000 tracks. Los dos se
      cumplen hoy con margen (ver la sección 4.5 de `ARQUITECTURA.md`)

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
- **`TaggingService`** (`services/tagging_service.py`, puro, sin Qt): funciones
  `bpm_bucket` / `key_value` / `energy_band` / `derived_tags` / `inherited_tags`, y el
  servicio con `sync_derived`, `sync_inherited`, `backfill_derived` y `backfill_inherited`
  (transacción única, reporte con contadores, callback de progreso)
- **AST de predicados** en `domain/query_ast.py`: los 9 operadores cerrados de la
  sección 4.4 de `ARQUITECTURA.md`, con validación estricta (operador, campo, forma y
  llaves inesperadas), `to_dict`/`parse` round-trip, `walk()` y `describe()` legible.
  `AST_VERSION = 1`. 61 tests
- **Compilador de AST a SQL** en `services/query_compiler.py`: cada nodo a un fragmento
  parametrizado (ningún valor del usuario llega a ser parte de la sentencia; hay un test
  que lo verifica con un `DROP TABLE` de prueba), `build_track_ids_query` y
  `build_count_query`. 45 tests, la mayoría ejecutando SQL de verdad contra una librería
  de prueba con casos borde (track sin analizar, `%` tipeado por el usuario, etc.)
- **Modelo de Collections** en `domain/collections.py`: `SmartCollection` (pila
  ordenada, inmutable, con `with_layer` / `without_layer` / `with_layer_toggled` /
  `with_layer_moved`), `QueryLayer`, `LayerMode`, `SortSpec` y `Crate`
- **Evaluador de la pila** en `services/collection_evaluator.py`: el fold
  `filter` / `exclude` / `union` compilado como cadena de CTEs, `sort` y `limit` una sola
  vez al final, paginado con `offset`, conteo por capa en una sola consulta y `explain()`
  para diagnosticar. 69 tests
- **Medición de rendimiento real** con `tools/bench_queries.py` y
  `tools/make_synthetic_library.py` (librería sintética de 50.000 tracks / 307.744 tags,
  con la distribución de BPM de la real). Ver la tabla de la sección 4.5 de
  `ARQUITECTURA.md`
- **`SqliteTagRepository`** (`storage/tag_repository.py`): vocabulario, asignaciones y
  `set_tags_for_source`, que es la operación que hace idempotente el recálculo — borra
  sólo filas de su propia fuente, así que lo manual nunca se toca
- **Backfill corrido sobre la librería real** (2026-09-09) con
  `tools/backfill_tags.py`: 2343 tags `derived` sobre los 781 analizados + 784 `inherited`
  = **3127 asignaciones, 0 errores, 0 tracks sin tag**. Segunda corrida: 0 cambios
  (idempotencia verificada sobre datos reales). Vocabulario resultante: 9 buckets de bpm,
  24 claves Camelot, 4 bandas de energía, 2 plataformas
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
- **404 tests pasan** (`pytest`, ~54 s), todos headless sobre servicios sin Qt
  (baseline de la sesión: 104)
- QA E2E en `qa_e2e.py`
- `WaveLoad.spec` de PyInstaller existente, `console=False`, con manejo de logging para
  builds sin consola

### En curso

- Paquete de contexto del proyecto (`ARQUITECTURA.md` + `ESTADO.md`) — esta sesión

### Pendiente

**Motor de Collections**
- Persistencia de collections y crates: el esquema está y el modelo de dominio también,
  falta el repositorio que los lea y escriba
- **Optimización identificada y medida, no implementada:** una capa cuyo predicado mira
  sólo columnas de análisis podría leer directo de `track_analysis` (322 ms → 156 ms en
  una pila de 3 capas sobre 50.000 tracks). No es correcta en general —un track sin fila
  de análisis desaparecería, y `bpm is_null` o un `range` bajo un `NOT` tienen que
  devolverlo— así que exige detectar antes que el predicado sea "positivo". Ver 4.5 de
  `ARQUITECTURA.md`
- Servicio de tagging **manual** (asignar/quitar desde la UI, individual y en lote)
- Enganchar `sync_derived` al final del análisis de un track y `sync_inherited` al
  import/descarga, para que un track nuevo nazca etiquetado sin correr el backfill
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
- Las conexiones SQLite se abren con `with db.get_connection() as conn`, que en sqlite3
  hace commit pero **no cierra**: las conexiones quedan vivas hasta que las recolecta el
  GC. En Windows eso impide borrar o mover el archivo de la base mientras el proceso
  vive. Patrón heredado de `SqliteTrackRepository`; `tools/backfill_tags.py` lo saltea con
  un `gc.collect()` explícito

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

**2. Distribución: alcance de plataformas y condiciones legales**
v1 es distribuible a otros DJs. Eso abre dos cosas nunca discutidas: si macOS entra o no,
y bajo qué términos se distribuye una aplicación que incorpora `yt-dlp` (licencias de las
dependencias, y las condiciones de uso de las plataformas de origen).

**3. ¿Existe "congelar a crate"?**
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
| 6. Criterio de rendimiento | 100 ms la primera página, 1 s el conteo por capa, medido sobre 50.000 tracks | Paginar puede cortar temprano y contar no: son dos operaciones con perfiles distintos |

---

## 5. Próximos 3 pasos

**1. Compilador de AST a SQL.**
`services/query_compiler.py`: cada nodo a un fragmento parametrizado (valores bindeados,
nunca interpolados). Los `tag` a `EXISTS (SELECT 1 FROM track_tags ...)`, los
`range`/`compare` a condiciones sobre `tracks` / `track_analysis`, los booleanos a
`AND`/`OR`/`NOT` anidados. Tests contra una DB temporal poblada.

**2. Evaluador de la pila de capas.**
El fold `filter` / `exclude` / `union` encadenado como CTEs, con `sort` y `limit` aplicados
una sola vez al final, y el conteo por capa que necesita el builder. Medir latencia contra
los 784 tracks reales, que ya tienen 3127 tags con qué filtrar de verdad.

**3. Enganchar el tagging automático al pipeline.**
`sync_derived` al terminar el análisis de un track y `sync_inherited` al importar o
descargar, para que un track nuevo nazca etiquetado sin depender del backfill manual.

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

### 2026-09-09 — unidad 3: TagService y backfill de tags automáticos
**Hecho:** `services/tagging_service.py` (lógica pura), `storage/tag_repository.py`
(persistencia) y `tools/backfill_tags.py` (script de corrida masiva, con `--dry-run` y
backup automático). 75 tests nuevos; suite total 223/223 en verde.

Corrida real sobre `waveload_library.db`, con backup previo
(`waveload_library.pre-backfill-20260909-133153.db`) y un dry-run sobre copia descartable
antes: **2343 tags `derived`** sobre los 781 tracks analizados (3 por track: bpm, clave,
energía) y **784 `inherited`** (plataforma de origen), total 3127 asignaciones, 0 errores,
ningún track sin tag. La segunda corrida reportó 0 cambios: la idempotencia está
verificada sobre datos reales, no sólo en tests.

**Decidido (provisional):**
- Buckets de BPM por década, con `under-100` y `170-plus` como extremos abiertos. El tag
  es para navegar y facetar; la precisión la da el nodo `range` sobre la columna.
- Bandas de energía `low` 1-3 / `mid` 4-6 / `high` 7-8 / `peak` 9-10. Sobre la librería
  real reparte 37 / 191 / 303 / 250, que es un reparto usable y no un histograma con un
  solo pico.
- Una clave que no matchea el patrón Camelot (`1..12` + `A`/`B`) no genera tag en vez de
  generar uno basura. Lo mismo un BPM fuera de 20–300.
- `source` y `playlist` son dos namespaces separados, no uno: son dos ejes distintos y
  filtrar por plataforma no es lo mismo que filtrar por playlist.

**Ojo para quien siga:** `source_playlist_name` está en NULL en los 784 tracks, así que el
namespace `playlist` existe en el código pero todavía no tiene un solo valor en la
librería. No es un bug del tagging: es que el pipeline de descarga nunca llenó esa
columna. Verificarlo antes de dar por rota la herencia de playlist.

**Bloqueado en:** nada.
**Siguiente:** el AST del motor de queries.

**`ARQUITECTURA.md` no cambió en esta unidad** (las decisiones de buckets y bandas son
parámetros de implementación, no arquitectura; quedan registradas acá).

### 2026-09-09 — unidad 4: AST de predicados
**Hecho:** `domain/query_ast.py` con los nueve operadores cerrados (`and`, `or`, `not`,
`tag`, `tag_any`, `range`, `compare`, `text`, `source`), constructores cómodos (`and_`,
`or_`, `tag`, `range_`, …), serialización `to_dict()` / `parse()` con round-trip
verificado para cada tipo de nodo, `walk()` en preorden y `describe()` legible.
61 tests nuevos; suite total 284/284 en verde.

**Decidido (provisional):**
- **El AST vive en `domain/`, no en `services/`.** Es estructura de datos con reglas de
  validación, no lógica de negocio, y `domain` es la capa sin dependencias hacia afuera —
  lo que permite que `services/query_compiler.py` dependa de él y no al revés. El
  compilador sí va en `services/`.
- **El parseo es estricto y falla fuerte.** Una llave inesperada, un operador desconocido o
  un rango invertido levantan `QueryASTError` con mensaje en castellano. Una collection
  guardada que no se puede evaluar tiene que decirlo; devolver resultados incompletos en
  silencio es peor que un error.
- `range` es un intervalo **cerrado** (min y max inclusive) y admite un solo extremo.
- El valor de un nodo `text` **no** se slugifica (a diferencia de un tag): es texto de
  búsqueda, no identidad.
- `in_collection` está fuera de v1 y hay un test que verifica que su AST es rechazado, no
  ignorado.

**Bloqueado en:** nada.
**Siguiente:** el compilador de AST a SQL.

**`ARQUITECTURA.md` no cambió en esta unidad**: el AST implementa exactamente la sección
4.4 tal como quedó escrita en la unidad 2.

### 2026-09-09 — unidad 5: compilador de AST a SQL, y la primera medición honesta
**Hecho:** `services/query_compiler.py` traduce cada nodo del AST a un fragmento de SQL
parametrizado sobre `tracks LEFT JOIN track_analysis`. El LEFT JOIN es lo que mantiene en
la librería a los tracks sin analizar (3 de los 784 reales); con un JOIN interno
desaparecerían de toda query. 45 tests nuevos, la mayoría ejecutando SQL contra una
librería de prueba. Suite total 329/329 en verde.

**Medición:** se generó una librería sintética de 50.000 tracks y 307.744 asignaciones de
tag (`tools/make_synthetic_library.py`, con la distribución de BPM de la librería real, no
uniforme) y se midió con `tools/bench_queries.py`. La primera versión del compilador daba
**1929 ms** en el peor predicado. Dos cambios lo bajaron a **518 ms**:

1. Sacar el `COALESCE` del predicado de nivel superior. Era redundante —un `WHERE` ya
   descarta las filas que dan NULL— y le impedía a SQLite usar el índice.
2. Compilar los nodos `tag` a `id IN (subconsulta)` en lugar de `EXISTS` correlacionado.
   El `EXISTS` se re-evalúa una vez por track; la subconsulta se materializa una sola vez.

Los dos están documentados con sus números en el código y en la sección 4.5 de
`ARQUITECTURA.md`.

**El hallazgo que importa:** el costo no está en materializar filas sino en recorrer.
`COUNT(*)` y traer todos los ids cuestan casi lo mismo (250 vs 275 ms), pero la primera
página (`LIMIT 200`) del mismo predicado cuesta **0,6 ms**, y la del predicado hostil
**22 ms**. O sea: una UI que pagina no tiene problema de latencia ni a 50.000 tracks. El
que sí lo tiene es el **conteo exacto por capa** del builder, porque un `COUNT` no puede
cortar temprano. Eso hay que resolverlo en el diseño del builder —conteo asincrónico o
aproximado—, no en el motor.

**Decidido (provisional):** el criterio de rendimiento (decisión abierta 6, ahora cerrada)
son dos presupuestos, no uno: **100 ms para la primera página** y **1 s para el conteo por
capa**, ambos medidos sobre una librería de 50.000 tracks. Los dos se cumplen hoy con
margen. La decisión de no cachear queda confirmada con evidencia, no con un argumento.

**Bloqueado en:** nada.
**Siguiente:** el evaluador de la pila de capas.

**Secciones de `ARQUITECTURA.md` que cambiaron:** 4.5 (dos detalles de compilación con sus
números, y la tabla de latencias medidas) y 5 (la fila de "sin caché" pasa a estar
confirmada con medición, y se agrega la fila del criterio de rendimiento).

### 2026-09-09 — unidad 6: modelo de Collections y evaluador de la pila de capas
**Hecho:** `domain/collections.py` (`SmartCollection`, `QueryLayer`, `LayerMode`,
`SortSpec`, `Crate`) y `services/collection_evaluator.py`, que compila el fold de capas a
una cadena de CTEs y lo ejecuta. Incluye paginado, conteo total, conteo por capa en una
sola consulta y `explain()`. 75 tests nuevos; suite total 404/404 en verde.

**Decidido (provisional):**
- **Las entidades son inmutables.** `with_layer`, `without_layer`, `with_layer_toggled` y
  `with_layer_moved` devuelven copias. Una pila de capas que se edita en el lugar hace
  imposible un "deshacer" y muy fácil que la UI y la DB se desincronicen.
- **Las posiciones se compactan al borrar y al mover.** Siempre son 0..n-1, sin huecos,
  que es lo que el índice UNIQUE `(collection_id, position)` del esquema espera.
- **`NULLS LAST` en el orden.** Un track sin analizar no debería encabezar un orden por
  BPM sólo por no tener BPM.

**Lo que la medición dijo y no era lo esperado:** el hallazgo de la unidad 5 —que paginar
es barato— **no se traslada a una pila de capas**. Sobre 50.000 tracks, la pila de ejemplo
de tres capas tarda 367 ms tanto para el resultado completo como para la primera página:
la cadena de CTEs obliga a materializar cada capa antes de poder cortar, y el `ORDER BY`
necesita el resultado entero. O sea: **el presupuesto de 100 ms para la primera página se
cumple con un predicado suelto y no se cumple con una pila de tres capas.** Queda anotado
como tal, sin mover el presupuesto para que dé.

Dos elisiones ya aplicadas bajaron esa pila de 399 ms a 367 ms: no emitir la CTE de la
base cuando la primera capa es `filter`, y no arrastrar el `LEFT JOIN track_analysis` en
capas que sólo miran tags. La tercera —leer directo de `track_analysis`— vale 2x pero no
es correcta en general y está documentada con su condición de aplicabilidad en 4.5.

**Bloqueado en:** nada.
**Siguiente:** el repositorio de collections y crates.

**Sección de `ARQUITECTURA.md` que cambió:** 4.5, con la tabla de latencias de la pila de
capas, las dos elisiones aplicadas y la optimización pendiente con su caveat.
