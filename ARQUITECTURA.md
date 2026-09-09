# WaveLoad — Arquitectura

> Documento de referencia estable. Cambia poco: solo cuando se toma o se revierte una
> decisión de arquitectura. El estado del trabajo vive en `ESTADO.md`.
>
> Convención: `[PENDIENTE: x]` marca algo que todavía no está decidido. No se rellena
> con suposiciones.

---

## 1. Qué es WaveLoad

WaveLoad es una aplicación de escritorio para Windows dirigida a DJs, que integra en un
solo flujo lo que hoy está partido entre tres o cuatro herramientas: buscar y descargar
material, limpiar sus metadatos, mantener la librería local y construir colecciones a
partir de ella. La diferencia con Rekordbox, Serato o Traktor no está en la
reproducción —WaveLoad no es un software de performance— sino en la etapa anterior: la
preparación. Rekordbox organiza con crates manuales y smart playlists de lógica plana
(una lista de condiciones unidas por AND u OR); WaveLoad organiza con un motor de tags y
queries por capas, donde una colección es una pila de filtros ordenada, inspeccionable y
editable capa por capa. A eso se suma que la descarga y el etiquetado están adentro del
mismo programa, no en un conversor web separado.

---

## 2. Principios de diseño

1. **La librería es la fuente de verdad, no la carpeta.** El estado vive en SQLite. El
   sistema de archivos es un detalle de almacenamiento, no la organización.
2. **La lógica de negocio no conoce Qt.** Todo lo que está en `services/`, `domain/` y
   `core/` es puro y testeable sin levantar una ventana. La UI consume, no decide.
3. **Nada destructivo sin reversa.** Las migraciones son idempotentes y transaccionales;
   la deduplicación conserva el registro más antiguo; se hacen backups de la DB antes de
   operaciones masivas.
4. **Determinismo antes que magia.** El análisis armónico, el scoring de transiciones y
   el ordenamiento de sets son algoritmos explicables con parámetros visibles, no cajas
   negras. Cuando entre IA, entra como una fuente de tags más, marcada como tal y
   distinguible de lo que puso el usuario.
5. **Todo lo que se muestra, funciona.** No hay entradas de navegación en estado
   "Próximamente". Si no está construido, no está en la UI (por eso "Colecciones" está
   oculto hoy en `ui/shell/sidebar.py`).
6. **Los datos del usuario sobreviven a WaveLoad.** Los tags se escriben también al ID3
   del archivo. Si el programa desaparece, el trabajo de curaduría no se pierde.
7. **Una sola fuente de configuración.** `SettingsService` es la única autoridad sobre
   ajustes; ningún módulo lee configuración por su cuenta.
8. **Escala objetivo: 50.000+ tracks.** Toda decisión de consulta u organización se juzga
   contra ese número, no contra los 784 tracks de la librería actual.

---

## 3. Modelo de dominio

### Entidades existentes

| Entidad | Qué es | Atributos principales |
|---|---|---|
| `Track` | Agregado raíz. La entrada permanente de la librería. | `id` (UUID), `title`, `artist`, `album`, `duration`, `created_at`, `updated_at`, `source_platform`, `source_playlist_name`, `source_playlist_id`, `source_url`, `bpm`, `key_camelot`, `energy` |
| `TrackAsset` | Archivo físico o dato asociado a un Track. | `id`, `track_id`, `asset_type` (`AUDIO_MP3`/`AUDIO_WAV`/`AUDIO_FLAC`/`THUMBNAIL`), `file_path` (UNIQUE en DB), `created_at`, `updated_at` |
| `DownloadItem` | Tarea transitoria de la cola de descarga. Vive solo mientras dura la descarga. | `id`, `url`, `title`, `output_dir`, `state`, `progress_text`, `retry_count`, `max_retries`, `final_mp3_path`, `temp_download_path` |

`Track` y `DownloadItem` están deliberadamente separados: uno es la librería permanente,
el otro es estado de cola. El puente es el evento `TrackDownloadedEvent`, que
`TrackService` convierte en `Track`. **No se deben fusionar.**

### Entidades del motor de Collections (a construir)

| Entidad | Qué es | Atributos principales |
|---|---|---|
| `Tag` | Etiqueta del vocabulario, con namespace. | `id`, `namespace`, `value` (único por par) |
| `TagAssignment` | Asignación de un tag a un track, con su procedencia. | `track_id`, `tag_id`, `source` (`manual`/`derived`/`inherited`/`ai`), `confidence`, `created_at` |
| `SmartCollection` | Colección dinámica: pila ordenada de capas de query. Se re-evalúa siempre. | `id`, `name`, `layers[]`, `sort`, `limit`, `created_at`, `updated_at` |
| `QueryLayer` | Una capa de la pila. | `id`, `collection_id`, `position`, `enabled`, `mode` (`filter`/`exclude`/`union`), `ast` (JSON) |
| `Crate` | Colección manual: lista ordenada y fija de tracks. | `id`, `name`, `created_at`, `updated_at` |
| `CrateEntry` | Un track dentro de un crate, con su posición. | `crate_id`, `track_id`, `position` |

`SmartCollection` y `Crate` son entidades **separadas**, no dos modos de una misma cosa.
Una smart collection no admite tracks fijados a mano ni exclusiones puntuales: si querés
control manual sobre el resultado, se materializa a un crate.

**Sí existe "congelar a crate", y el crate no guarda referencia a su origen.**
`CollectionService.freeze_to_crate()` evalúa la collection y materializa el resultado en un
crate nuevo. Es el puente entre las dos entidades: como una smart collection no admite
tracks fijados a mano, congelar es la salida cuando hace falta control manual sobre el
resultado.

El crate resultante es **independiente** desde el momento en que se crea: no apunta a la
collection de origen, y ésta puede cambiar o borrarse sin que el crate se entere. Guardar
la referencia obligaría a decidir qué pasa cuando la collection cambia —¿se re-materializa,
se avisa, se marca como desactualizado?— y cualquiera de esas respuestas reintroduce por la
ventana la ambigüedad que separar las dos entidades vino a sacar. El nombre por defecto
(`"<collection> (congelada)"`) deja el rastro donde importa: en algo que el usuario lee, no
en una foreign key que el sistema tenga que mantener.

```mermaid
erDiagram
    Track ||--o{ TrackAsset : "tiene"
    Track ||--o| TrackAnalysis : "tiene"
    Track ||--o| TrackEmbedding : "tiene"
    Track ||--o{ TagAssignment : "recibe"
    Tag ||--o{ TagAssignment : "se asigna via"
    Track ||--o{ CrateEntry : "aparece en"
    Crate ||--o{ CrateEntry : "contiene"
    SmartCollection ||--o{ QueryLayer : "apila"

    Track {
        uuid id PK
        string title
        string artist
        string album
        int duration
        string source_platform
        string source_playlist_name
        string source_playlist_id
        string source_url
    }
    TrackAsset {
        uuid id PK
        uuid track_id FK
        enum asset_type
        string file_path UK
    }
    TrackAnalysis {
        uuid track_id PK
        real bpm
        string musical_key
        real energy_level
        string analyzed_at
    }
    TrackEmbedding {
        uuid track_id PK
        blob embedding_vector
        string model_version
    }
    Tag {
        int id PK
        string namespace
        string value
    }
    TagAssignment {
        uuid track_id FK
        int tag_id FK
        enum source
        real confidence
    }
    SmartCollection {
        int id PK
        string name
        json sort
        int limit_n
    }
    QueryLayer {
        int id PK
        int collection_id FK
        int position
        bool enabled
        enum mode
        json ast
    }
    Crate {
        int id PK
        string name
    }
    CrateEntry {
        int crate_id FK
        uuid track_id FK
        int position
    }
    DownloadItem {
        string id PK
        string url
        enum state
        int retry_count
    }
```

`DownloadItem` queda fuera del diagrama de relaciones a propósito: no tiene clave foránea
a `Track`. La única conexión entre ambos es el evento `TrackDownloadedEvent`.

---

## 4. El motor de tags/queries por capas

Esta es la fundación del producto. Todo lo demás —el grafo, el set builder, los exports—
consume lo que este motor produce.

### 4.1 Tags: namespace y valor

Un tag es siempre `namespace:value`. El namespace es vocabulario controlado (el conjunto
de namespaces se define una vez y es cerrado en el uso diario); el valor es libre dentro
de su namespace. Ejemplos: `genre:techno`, `mood:dark`, `context:peak-time`,
`energy:high`.

Que el namespace sea obligatorio es lo que hace legibles y componibles las capas de
query: una capa opera sobre un eje, no sobre una nube de etiquetas sueltas.

**Namespaces de v1 (lista cerrada).** Definidos en `domain/tags.py`, que es la única
autoridad sobre el vocabulario:

| Namespace | Producido por | Para qué |
|---|---|---|
| `genre` | manual + ai | Género musical |
| `mood` | manual + ai | Carácter del track (`dark`, `euphoric`, `hypnotic`) |
| `context` | manual | Dónde entra en un set (`warmup`, `peak-time`, `closing`) |
| `status` | manual | Estado de curaduría (`to-review`, `ready`, `already-played`) |
| `bpm` | derived | Bucket de tempo (`120-129`) |
| `key` | derived | Código Camelot (`8a`) |
| `energy` | derived | Banda de energía (`low`/`mid`/`high`/`peak`) |
| `source` | inherited | Plataforma de origen (`youtube`, `local`) |
| `playlist` | inherited | Playlist de origen |

El usuario crea **valores** libremente dentro de cada namespace; **no crea namespaces**
desde la UI en v1. Los namespaces `derived` e `inherited` no son editables a mano: se
recalculan. Agregar un namespace es agregar una línea a la tupla `NAMESPACES` — no
requiere migración, porque la columna es TEXT.

Los valores se normalizan a slug minúsculo con guiones (`"Peak Time"` -> `peak-time`,
`"Drum & Bass"` -> `drum-bass`), de modo que la identidad de un tag es su slug y la UI
puede mostrar una versión bonita encima. Esto evita que `Techno`, `techno` y `TECHNO` sean
tres tags distintos, que es exactamente cómo se degradan los sistemas de tags libres.

### 4.2 Procedencia de los tags

Cada asignación guarda de dónde salió. Las cuatro fuentes de v1:

| `source` | Origen | Estado |
|---|---|---|
| `manual` | El usuario etiqueta desde la librería o el context panel, individual o en lote. | A construir |
| `derived` | Se derivan del análisis que ya corre: `bpm`, `key_camelot`, `energy` → tags. 781 de 784 tracks ya están analizados. | Análisis hecho; derivación a construir |
| `inherited` | `source_platform` y `source_playlist_name` se convierten en tags al importar o descargar. Las columnas ya existen y se pueblan. | A construir |
| `ai` | Clasificación automática de género/mood por modelo. Depende de `track_embeddings`, hoy en 0 filas. | No existe nada. Es el ítem de mayor riesgo de v1 — ver `ESTADO.md` |

Los tags `derived` se recalculan cuando se re-analiza un track; los `manual` nunca se
tocan automáticamente.

**Política de conflicto: coexisten, y lo automático nunca pisa lo manual.** La clave
primaria de `track_tags` es `(track_id, tag_id, source)`, así que un mismo tag puede estar
asignado por dos fuentes a la vez y ninguna sobrescribe a la otra. Un recálculo de tags
`derived` borra *sólo* las filas con `source = derived` de ese track y las vuelve a
escribir; jamás toca `manual`. Si el usuario puso `genre:minimal` y la IA propone
`genre:techno`, el track queda con los dos, cada uno con su procedencia visible, y es el
usuario quien decide si borra alguno. La alternativa —que el manual bloquee futuras
asignaciones automáticas en ese namespace— se descartó porque convierte un acto de
etiquetado en una configuración invisible y persistente.

`[PENDIENTE: umbral de confianza mínimo para materializar un tag de IA, y si los tags de
IA se muestran visualmente distintos de los manuales.]`

### 4.3 Las capas

Una `SmartCollection` es una **pila ordenada de capas**. La base implícita es la librería
completa. Cada capa recibe el conjunto que produjo la anterior y lo transforma según su
`mode`:

- `filter` — se queda con los tracks del conjunto que cumplen el predicado (intersección).
- `exclude` — saca del conjunto los que cumplen el predicado (diferencia).
- `union` — agrega al conjunto los tracks de la librería que cumplen el predicado.

Cada capa tiene `enabled`, así que se apaga y se prende sin borrarla, y `position`, así
que se reordena. Reordenar cambia el resultado cuando hay capas `union` involucradas: el
orden es semántico, no cosmético.

Ejemplo de una pila de tres capas:

```
base:  librería completa                             → 784
[1] filter   genre:techno OR genre:minimal           → 210
[2] filter   bpm BETWEEN 122 AND 128                 →  94
[3] exclude  context:already-played                  →  71
```

El valor frente al AND/OR plano de una smart playlist de Rekordbox es que cada paso
intermedio es visible y desactivable: se puede apagar la capa 2 y ver inmediatamente qué
aportaba, sin reescribir la condición entera.

`sort` y `limit` se aplican **una sola vez, al final**, sobre el resultado del fold, no
por capa.

### 4.4 El predicado: AST

Cada capa lleva un predicado guardado como AST en JSON. No se guarda texto: el texto —si
más adelante hay un DSL— es una vista sobre el AST, igual que el builder visual. Ambas
interfaces editan la misma estructura.

Tipos de nodo:

- `bool` — `{"op": "and"|"or"|"not", "children": [...]}`
- `tag` — `{"op": "tag", "namespace": "genre", "value": "techno"}`
- `tag_any` — presencia de cualquier valor en un namespace: `{"op": "tag_any", "namespace": "mood"}`
- `range` — sobre campo numérico: `{"op": "range", "field": "bpm", "min": 122, "max": 128}`
- `compare` — `{"op": "compare", "field": "duration", "cmp": "gt", "value": 300}`
- `text` — búsqueda sobre `title` / `artist` / `album`
- `source` — sobre procedencia del track (`source_platform`, `source_playlist_name`)

**Lista cerrada de v1.** Operadores: `and`, `or`, `not`, `tag`, `tag_any`, `range`,
`compare`, `text`, `source`. Comparadores de `compare`: `eq`, `ne`, `lt`, `lte`, `gt`,
`gte`, `is_null`, `not_null`. Modos de `text`: `contains` (default), `equals`,
`starts_with`.

Campos consultables, todos sobre columnas que ya existen:

| Campo | Origen | Tipo |
|---|---|---|
| `bpm` | `track_analysis.bpm` | numérico |
| `energy` | `track_analysis.energy_level` | numérico |
| `duration` | `tracks.duration` | numérico |
| `title`, `artist`, `album` | `tracks` | texto |
| `source_platform`, `source_playlist_name` | `tracks` | texto (nodo `source`) |
| `created_at` | `tracks.created_at` | fecha ISO-8601 |
| `analyzed_at` | `track_analysis.analyzed_at` | fecha ISO-8601 |

**Predicados temporales: sí, pero sólo sobre columnas existentes.** `created_at` y
`analyzed_at` se consultan con `range`/`compare` comparando strings ISO-8601, que en ese
formato ordena igual que la fecha. `never_played` queda fuera de v1: no hay historial de
reproducción y agregarlo sería inventar una columna sin quién la escriba.

**`in_collection`: fuera de v1.** Referenciar una collection desde otra invita ciclos,
obliga a detección de ciclos y a compilación recursiva, y la pila de capas ya cubre el
caso común. Agregarlo después es aditivo —un tipo de nodo nuevo y un bump de
`ast_version`— y no requiere migración.

`is_null` / `not_null` sobre `bpm` cubren "tracks todavía sin analizar" sin necesidad de
un operador dedicado.

El AST se versiona con un campo `ast_version` para poder migrar la forma del JSON sin
romper colecciones guardadas.

### 4.5 Evaluación

La evaluación es una compilación, no un recorrido en memoria:

1. Se lee la pila de capas ordenada por `position`, salteando las que tienen
   `enabled = false`.
2. Cada AST se compila a un fragmento de SQL parametrizado. Los nodos `tag` se traducen a
   `EXISTS (SELECT 1 FROM track_tags ...)`; los `range` / `compare` a condiciones sobre
   columnas de `tracks` / `track_analysis`; los `bool` a `AND` / `OR` / `NOT` anidados.
3. Las capas se encadenan como CTEs sucesivas: `layer_0` es la librería, `layer_n` se
   define en términos de `layer_n-1` según su `mode` (intersección para `filter`, `EXCEPT`
   para `exclude`, `UNION` para `union`).
4. `sort` y `limit` se aplican al `SELECT` final.
5. SQLite ejecuta. Los valores viajan siempre como parámetros bindeados, nunca
   interpolados en el string.

No hay caché ni materialización de resultados: una smart collection se recalcula cada vez
que se abre. Con índices sobre `track_tags(tag_id, track_id)`, `track_tags(track_id)` y
sobre las columnas de análisis, esto se sostiene en el orden de magnitud objetivo. Si en
la práctica no se sostiene, la salida es materializar por collection con invalidación por
evento, no cambiar el modelo.

**Dos detalles de compilación que valen 4x** (medidos, no supuestos —
`tools/bench_queries.py` sobre una librería sintética de 50.000 tracks y 307.744
asignaciones generada con `tools/make_synthetic_library.py`):

1. **El predicado de nivel superior no se envuelve en `COALESCE`.** Un `WHERE` ya descarta
   las filas que evalúan a NULL, así que envolverlo es redundante — y le impide a SQLite
   usar el índice de la columna. Sólo el `NOT` necesita el colapso a dos valores, y lo
   aplica sobre su propio hijo.
2. **Los nodos `tag` se compilan a `id IN (subconsulta)`, no a `EXISTS` correlacionado.**
   Semánticamente equivalentes (`track_tags.track_id` es parte de la PK, nunca es NULL),
   pero el `EXISTS` se re-evalúa una vez por track mientras que la subconsulta se
   materializa una vez y SQLite la cruza con un filtro de Bloom.

Juntos bajan el peor caso medido de 1929 ms a 518 ms sobre 50.000 tracks, y la pila de
ejemplo de 4.3 de 579 ms a 80 ms.

**Latencia medida** (peor caso de 15 corridas):

| Escenario | 784 tracks (librería real) | 50.000 tracks (sintética) |
|---|---|---|
| Un tag derivado | 1,6 ms | 72 ms |
| Rango de BPM | 1,1 ms | 296 ms |
| La pila de ejemplo de 4.3 | 1,8 ms | 80 ms |
| Predicado hostil (8 tags en OR + rango + 2 negaciones) | 3,4 ms | 518 ms |
| **Primera página (`LIMIT 200`) del predicado hostil** | — | **22 ms** |
| **Primera página del rango de BPM** | — | **0,6 ms** |

Lo que la tabla dice es que **el costo no está en materializar filas sino en recorrer**:
`COUNT(*)` y traer todos los ids cuestan casi lo mismo (250 ms vs 275 ms para el rango de
BPM), mientras que la primera página cuesta tres órdenes de magnitud menos.

**Pero eso vale para un predicado suelto, no para una pila de capas.** Medido sobre la
misma librería sintética, la pila de ejemplo de 4.3 —tres capas— da:

| Operación (3 capas, 50.000 tracks) | Mediana |
|---|---|
| Resultado completo (4991 filas, ordenado por BPM) | 367 ms |
| Primera página `LIMIT 200`, ordenada | 367 ms |
| Primera página `LIMIT 200`, sin orden | 286 ms |
| Conteo total | 321 ms |
| Conteo por capa (una sola consulta) | 670 ms |

El `LIMIT` casi no ayuda: la cadena de CTEs obliga a materializar cada capa antes de poder
cortar, y con un `ORDER BY` el resultado completo tiene que existir antes de tomar las
primeras 200 filas. **El presupuesto de 100 ms para la primera página se cumple con un
predicado suelto y no se cumple con una pila de tres capas a 50.000 tracks.** Está medido,
no estimado, y es lo primero a atacar cuando el builder exista.

**Dos elisiones que ya están aplicadas** (y que bajaron esa pila de 399 ms a 367 ms):

- La CTE de la base no se emite cuando la primera capa activa es `filter`: intersecar con
  la librería completa es no intersecar con nada.
- El `LEFT JOIN track_analysis` sólo entra en las capas cuyo predicado mira `bpm`,
  `energy` o `analyzed_at`. Una capa que sólo filtra por tags no lo necesita, y
  arrastrarlo cuesta 2,3x.

**La optimización que falta, y por qué no está hecha:** una capa cuyo predicado mira
*sólo* columnas de análisis podría leer directo de `track_analysis` sin pasar por `tracks`
(medido a mano: 322 ms → 156 ms en esa misma pila). No se implementó porque no es
correcta en general: un track sin fila en `track_analysis` desaparecería de la consulta, y
hay predicados que deben devolverlo —`bpm is_null`, o cualquier `range` adentro de un
`NOT`—. Aplicarla exige detectar antes que el predicado sea "positivo": sin `is_null` y
sin `NOT` por encima. Es una optimización real con una condición de aplicabilidad real,
no un olvido.

### 4.6 Persistencia

Todo vive en la misma base SQLite de la librería (`waveload_library.db`), agregado por
migración idempotente como las que ya corren en `infrastructure/database.py`:

```
tags(id, namespace, value)                                      UNIQUE(namespace, value)
track_tags(track_id, tag_id, source, confidence, created_at)    PK(track_id, tag_id, source)
collections(id, name, sort_json, limit_n, ast_version, created_at, updated_at)
collection_layers(id, collection_id, position, enabled, mode, ast_json)
crates(id, name, created_at, updated_at)
crate_entries(crate_id, track_id, position)                     PK(crate_id, track_id)
```

**Estos nombres están congelados.** La migración
(`DatabaseManager._migrate_collections_schema`) ya corrió contra la librería real el
2026-09-09; renombrar una tabla o una columna a partir de acá cuesta una migración de
datos. La forma exacta, con los `created_at` que el resumen de arriba omitía:

```
tags(id, namespace, value, created_at)                          UNIQUE(namespace, value)
track_tags(track_id, tag_id, source, confidence, created_at)    PK(track_id, tag_id, source)
collections(id, name, sort_json, limit_n, ast_version, created_at, updated_at)  name UNIQUE
collection_layers(id, collection_id, position, enabled, mode, ast_json)
crates(id, name, created_at, updated_at)                                        name UNIQUE
crate_entries(crate_id, track_id, position)                     PK(crate_id, track_id)
```

Índices: `idx_track_tags_tag(tag_id, track_id)`, `idx_track_tags_track(track_id)`,
`idx_track_tags_source(source)`, `idx_tags_namespace(namespace)`,
`idx_collection_layers_position(collection_id, position)` UNIQUE,
`idx_crate_entries_crate(crate_id, position)`, más `idx_track_analysis_bpm` e
`idx_track_analysis_energy`, que son contra los que pegan los nodos `range` / `compare`.

La migración es puramente aditiva: cada sentencia es `IF NOT EXISTS` y ninguna lee,
reescribe ni borra una fila de la librería existente.

### 4.7 Salida al archivo (ID3)

Los tags se escriben también al ID3 del MP3 con Mutagen, para que la curaduría sobreviva a
WaveLoad. La escritura es un efecto secundario asíncrono de la asignación, nunca bloquea
la UI, y la DB sigue siendo la fuente de verdad: si el archivo y la DB difieren, gana la
DB.

**Frame elegido: `TXXX:WAVELOAD_TAGS`**, un frame de usuario con clave propia que
contiene la lista completa de tags `namespace:value` separados por `;`. Es el único de los
tres candidatos que es *aditivo*: no pisa nada que el usuario o su DJ software hayan
escrito. `GRP1` se descartó como destino primario porque Rekordbox lo lee como "Grouping"
—que es justamente por qué tentaba— pero también porque **ya puede tener contenido del
usuario**, y sobrescribirlo en una escritura masiva viola el principio 3. `COMM` tiene el
mismo problema y además es multilingüe y ambiguo.

Escribir a `GRP1` queda como **mirror opcional**: un ajuste apagado por defecto, para
quien prefiera que sus tags aparezcan dentro de Rekordbox sin importar nada y acepte que
se le pise el campo Grouping. Esa parte no es v1.

**Lectura: sí, pero sólo al importar un archivo que todavía no está en la librería.** En
ese caso no hay conflicto posible —no existe fila en la DB que pueda ganar— y se
reconstruyen los tags con `source = manual`, que es lo que eran cuando se escribieron.
Para un archivo que ya está en la librería no se relee nunca el ID3: la DB es la fuente de
verdad, y una re-lectura sería exactamente el camino por el que un archivo desactualizado
resucita tags que el usuario ya había borrado.

---

## 5. Decisiones de arquitectura

| Decisión | Alternativas descartadas | Por qué | Qué la revertiría |
|---|---|---|---|
| **Motor de tags/queries por capas** como fundación de la organización | (1) Modelo de grafos; (2) smart albums estilo Rekordbox; (3) canvas espacial; (4) línea de tiempo | (1) Muy flexible pero demasiado abstracto para flujos rápidos de DJing y difícil de visualizar de forma lineal. (2) Lógica rígida AND/OR plana, sin profundidad ni contexto por capas. (3) Bueno para ordenamiento visual táctil, deficiente para consultas estructuradas sobre 50.000+ tracks. (4) Sirve para secuenciar un set puntual, no escala como motor primario de biblioteca. El motor por capas es el único desacoplado y mantenible a largo plazo | Que en uso real las queries terminen siendo siempre de una sola capa: significaría que el modelo es sobreingeniería y que un smart album plano alcanzaba |
| **Capas apilables** como forma de la query | Una sola expresión booleana AND/OR/NOT | Cada paso intermedio es visible, desactivable y reordenable. Permite entender por qué un track está o no está en el resultado, que es exactamente donde falla la smart playlist tradicional | Que reordenar y desactivar capas no se use nunca en la práctica |
| **`SmartCollection` y `Crate` como entidades separadas** | Modelo unificado (query dinámica + pins + exclusiones en una sola entidad) | Semántica sin ambigüedad en cada una: una es dinámica y siempre viva, el otro es una lista fija que no cambia sola. Familiar para quien viene de Rekordbox | Que en la práctica todas las smart collections terminen convertidas a crates para poder tocarlas a mano: indicaría que hacía falta el híbrido con pins |
| **Query persistida como AST en JSON, compilada a SQL** | (a) DSL de texto parseado en runtime; (b) evaluación en memoria en Python | El AST es la representación única que alimenta tanto un builder visual como un futuro DSL. Compilar a SQL delega el trabajo a SQLite, que es lo que escala a 50.000+ tracks; evaluar en Python obligaría a cargar la librería entera en memoria | Que aparezcan predicados no expresables en SQL (por ejemplo similitud por embeddings), forzando un paso híbrido de evaluación en Python |
| **Sin caché ni materialización de resultados** *(confirmada con medición, 2026-09-09)* | Materializar el resultado de cada collection con invalidación por evento | Un recálculo siempre correcto es preferible a una caché que puede quedar desincronizada. Ya no es sólo un argumento: medido sobre 50.000 tracks sintéticos, la primera página de resultados sale en 0,6–22 ms y el peor predicado completo en 518 ms (ver 4.5) | Que el conteo exacto por capa, que es el único caso que no puede cortar temprano, resulte inusable en el builder. La salida sería materializar el conteo, no el resultado |
| **Criterio de rendimiento: 100 ms para la primera página, 1 s para el conteo por capa, medido sobre 50.000 tracks** *(provisional, 2026-09-09)* | (a) Sin criterio; (b) un solo número para toda evaluación | Son dos operaciones con perfiles distintos: paginar puede cortar temprano y contar no. Un solo número obligaría a fijarlo en el peor de los dos y a rediseñar por una operación que corre en segundo plano. La librería de referencia son 50.000 tracks porque es la escala objetivo declarada, no los 784 de hoy | Que el uso real muestre que el conteo por capa tiene que ser instantáneo para que el builder se sienta bien: ahí el presupuesto de 1 s no alcanza y hay que materializar el conteo |
| **Tags namespaced `key:value`, namespaces controlados** | (a) Tags planos libres; (b) namespaces y valores ambos fijados por esquema | Los planos se desordenan solos apenas la librería crece. Controlar también los valores obliga a editar un esquema antes de poder etiquetar, lo que rompe el flujo rápido | Que la cantidad de namespaces crezca tanto que dejen de ser vocabulario y pasen a ser ruido |
| **Los tags se escriben también al ID3** | (a) Solo en la DB de WaveLoad; (b) materializarlos únicamente al exportar | El trabajo de curaduría es lo más caro de reproducir y tiene que sobrevivir a la herramienta. Mutagen ya está en el stack | Corrupción o pérdida de metadata en escritura masiva; o que la escritura resulte demasiado lenta sobre librerías grandes |
| **Grafo y set builder como consumidores de Collections** | (a) Congelarlos fuera de v1; (b) mantenerlos como workspaces independientes | Dejan de competir con Collections como modelo de organización y pasan a ser una salida: se arma una collection y desde ahí se genera el grafo o el set. Conserva el código ya construido y probado | Que la integración cueste más que el valor que aporta: en ese caso se congelan |
| **Namespaces cerrados: 9 en v1, el usuario crea valores pero no namespaces** *(provisional, 2026-09-09)* | (a) Namespaces libres desde el arranque; (b) namespaces y valores ambos fijos | Nueve ejes cubren lo que hoy hay con qué llenar: tres los produce el análisis, dos el origen, cuatro el usuario. Dejar crear namespaces desde la UI antes de saber cuáles se usan de verdad garantiza un vocabulario roto a los tres meses. Abrirlos después es agregar un botón; cerrarlos después es migrar datos | Que al usar la app aparezca repetidamente un eje que no entra en ninguno de los nueve. La salida es agregar una línea a `NAMESPACES`, no abrir la creación al usuario |
| **Valores de tag normalizados a slug** *(provisional, 2026-09-09)* | Guardar el texto tal como lo tipeó el usuario | La identidad de un tag tiene que ser insensible a mayúsculas, espacios y puntuación, o `Techno` / `techno` / `TECHNO` se vuelven tres tags. La UI puede mostrar una etiqueta bonita encima del slug | Que los usuarios quieran valores con tipografía significativa que el slug destruya |
| **Lo automático nunca pisa lo manual; los tags de distinta fuente coexisten** *(provisional, 2026-09-09)* | (a) Gana el manual y borra lo automático; (b) el manual bloquea el namespace para fuentes automáticas | La PK `(track_id, tag_id, source)` ya lo permite sin costo. Un recálculo de `derived` borra sólo filas `derived`. Bloquear un namespace convierte un acto de etiquetado en configuración invisible | Que en la práctica la coexistencia genere ruido visual insoportable en tracks muy etiquetados |
| **AST de v1 con lista cerrada de 9 operadores y 10 campos; sin `in_collection`** *(provisional, 2026-09-09)* | (a) Incluir `in_collection` desde v1; (b) dejar la lista abierta y agregar operadores sobre la marcha | Todos los campos elegidos existen hoy como columna: nada del compilador depende de datos que no están. `in_collection` obliga a detección de ciclos y compilación recursiva por un caso que la pila de capas ya cubre, y agregarlo después es aditivo (nodo nuevo + bump de `ast_version`) | Que aparezca la necesidad real de componer colecciones entre sí, o un predicado frecuente que no se pueda expresar con los nueve operadores |
| **Predicados temporales sólo sobre `created_at` y `analyzed_at`** *(provisional, 2026-09-09)* | (a) Sin predicados temporales; (b) agregar columnas de historial (`last_played_at`, `play_count`) | Esas dos columnas ya existen y ya se pueblan; compararlas como strings ISO-8601 ordena igual que la fecha, sin código extra. `never_played` requeriría inventar una columna sin quién la escriba | Que se construya reproducción o historial de sets: ahí las columnas tendrían un productor real |
| **Tags al ID3 en `TXXX:WAVELOAD_TAGS`** *(provisional, 2026-09-09)* | (a) `GRP1` (Rekordbox lo lee como Grouping); (b) `COMM` | Es el único destino aditivo: no pisa nada que el usuario o su DJ software hayan escrito. `GRP1` y `COMM` pueden tener contenido previo, y sobrescribirlo en una escritura masiva viola el principio 3 | Que la prioridad pase a ser que los tags se vean dentro de Rekordbox sin importar nada. La salida ya está prevista: mirror opcional a `GRP1`, apagado por defecto |
| **El ID3 se lee sólo al importar un archivo que no está en la librería** *(provisional, 2026-09-09)* | Sincronización bidireccional permanente entre archivo y DB | En un archivo nuevo no hay conflicto posible, así que reconstruir sus tags es gratis. Releer el ID3 de un archivo ya presente es el camino por el que un archivo desactualizado resucita tags que el usuario borró | Que aparezca un flujo real de edición de tags fuera de WaveLoad que haya que reconciliar |
| **"Congelar a crate" existe, y el crate queda independiente** *(provisional, 2026-09-09)* | (a) No tener la acción; (b) que el crate guarde una FK a la collection de origen | Es la salida prevista para cuando hace falta control manual sobre el resultado de una query. Guardar la referencia obliga a decidir qué pasa cuando la collection cambia, y cualquier respuesta reintroduce la ambigüedad que separar las dos entidades vino a sacar. El rastro queda en el nombre por defecto, que es algo que el usuario lee | Que los usuarios pidan repetidamente "actualizar este crate desde su collection": ahí la referencia se gana su costo |
| **`Track` y `DownloadItem` separados** | Una sola entidad con estado de cola y de librería | Uno es permanente y desacoplado de cómo se obtuvo el archivo; el otro es transitorio y carga progreso, reintentos y rutas temporales. Fusionarlos contamina la librería con estado de descarga | Nada previsto. Está documentado en el código como decisión explícita a no revertir |
| **Servicios puros, sin Qt** | Lógica dentro de los widgets | Permite testear headless: hoy 104 tests corren sin levantar una ventana | Nada previsto |
| **SQLite local como único repositorio persistente**, con inyección de dependencias | Base embebida alternativa; capa ORM; backend remoto | Un archivo, sin servidor, sin cuenta, sin conexión. La inyección permite sustituir el repositorio en tests | Necesidad real de sincronizar entre máquinas |
| **`SettingsService` como única fuente de verdad de configuración** | Configuración leída ad-hoc por cada módulo | Ya resolvió el problema de rutas divergentes según cómo se lanzaba la app | Nada previsto |

---

## 6. Stack técnico

| Pieza | Por qué |
|---|---|
| **Python 3.13** | Ecosistema de audio (librosa, mutagen) y de descarga (yt-dlp) sin equivalente en otro runtime |
| **PySide6 (Qt 6)** | UI de escritorio nativa con licencia LGPL; grillas de alto rendimiento vía modelo/delegate, necesarias para decenas de miles de filas |
| **SQLite** | Sin servidor, un archivo, transaccional. Es además lo que hace viable compilar las queries por capas a SQL |
| **yt-dlp** | Motor de descarga; el único que se mantiene al día con los cambios de las plataformas |
| **FFmpeg** | Conversión y extracción de audio. Dependencia externa del sistema, no un paquete de Python |
| **Mutagen** | Lectura y escritura de ID3. Es lo que permite que los tags viajen con el archivo |
| **librosa + soundfile** | BPM por beat tracking, cromas para tonalidad, RMS para energía |
| **NetworkX** | Grafo de conocimiento: layout force-directed, detección de comunidades, caminos mínimos |
| **aiohttp** | Descargas concurrentes asíncronas |
| **browser-cookie3** | Cookies del navegador para contenido que requiere sesión |
| **Pillow** | Procesamiento de carátulas antes de embeberlas |
| **pytest** | Suite headless sobre los servicios puros |
| **PyInstaller** | Empaquetado a `.exe` sin Python instalado (`WaveLoad.spec`, `console=False`) |

### Estructura de capas

```
domain/          entidades y contratos de repositorio; sin dependencias hacia afuera
application/     casos de uso y bootstrap (import_use_case, analysis_coordinator)
services/        lógica de negocio pura, sin Qt (análisis, similitud, grafo, sets, export)
infrastructure/  DB, esquema, migraciones, autenticación de navegador
storage/         implementaciones concretas de repositorio (SqliteTrackRepository) y stores
core/            descarga, cola, máquina de estados, event bus, config, utils
workers/         hilos Qt que envuelven a los servicios sin contener lógica
ui/              shell, workspaces, componentes, design system (theme/)
```

La comunicación entre la lógica y la UI pasa por el **event bus**
(`core/event_bus.py`): `TrackDownloadedEvent`, `TrackCreatedEvent`. La UI no llama a la
descarga, y la descarga no conoce a la UI.

### Algoritmos ya fijados (parámetros de referencia)

- **Compatibilidad armónica**: rueda Camelot, ventana de BPM ±12%, categorías 0–5 (misma
  clave, relativa, ±1 paso, +2 "boost", +7 "subidón"), resultados interleaved por
  categoría en round-robin.
- **Score de transición**: pesos BPM 0.35 / clave 0.25 / energía 0.15, renormalizados
  sobre las dimensiones disponibles. Género, danceability e historial están declarados con
  peso 0 porque esos datos todavía no existen.
- **Grafo**: umbral de score 70, tope de 6 aristas por nodo (k-NN), layout force-directed
  sembrado con las posiciones previas para que el mapa no salte entre builds.
- **Set builder**: greedy + 2-opt maximizando
  `mean_transition_value − λ · mean_squared_energy_deviation·100`, con λ = 0.6 y cuatro
  curvas de energía por evento (warmup, club, festival, afterhours).
- **Análisis**: perfiles Shaath para tonalidad, ventana de 90 s salteando los primeros
  15 s, sample rate 22.050 Hz, energía calibrada sobre RMS 0.08–0.34 y escalada a 1–10.

---

## 7. Fuera de alcance de v1

Explícito, para no rediscutirlo:

- **Separación de stems** (Demucs/Spleeter). Está en la visión a futuro, no en v1.
- **Generación de mashups y transiciones automáticas.**
- **Integración bidireccional con Rekordbox/Serato/Traktor/Ableton.** v1 exporta a M3U8 y
  XML de Rekordbox, en una sola dirección. No lee de vuelta el estado de esos programas.
- **Sincronización en la nube o entre máquinas.** La librería es local, de una máquina.
- **Multiusuario, colaboración o colecciones compartidas.**
- **Aplicación móvil o web.** WaveLoad es escritorio.
- **Reproducción para performance.** WaveLoad prepara música; no se toca en vivo con él.
- **Streaming.** No se integra con Spotify/Beatport como fuente de reproducción; el
  `spotify_resolver` existente resuelve metadata, no audio.
- **Recomendación por similitud sonora aprendida.** La similitud de v1 es determinista
  (BPM, Camelot, energía). Los embeddings quedan preparados en el esquema, sin uso más
  allá de lo que requiera el tagging por IA.

`[PENDIENTE: definir si macOS entra o queda fuera. Hoy todo el proyecto asume Windows
—rutas, empaquetado, browser-cookie3— pero nunca se decidió explícitamente.]`
