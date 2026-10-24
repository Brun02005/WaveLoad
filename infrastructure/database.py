import sqlite3
import logging
from pathlib import Path
from core.config import BASE_DIR

logger = logging.getLogger(__name__)

# Path for the library database. Anchored to BASE_DIR (frozen-aware, absolute)
# so it is deterministic — a bare relative path resolved against the current
# working directory, which split the library across two files depending on how
# the app was launched.
LIBRARY_DB_PATH = BASE_DIR / "waveload_library.db"

# Segundos que una conexión espera a que otra suelte el lock antes de fallar
# con "database is locked". La descarga, el auto-tagging y el análisis
# escriben desde hilos distintos.
_BUSY_TIMEOUT_S = 10


class _ClosingConnection(sqlite3.Connection):
    """Conexión que además de commitear/rollbackear al salir del ``with``, se
    cierra.

    El ``with`` de sqlite3 no cierra: la conexión quedaba viva hasta que la
    recolectaba el GC, y en Windows eso impide mover o respaldar la base
    mientras el proceso vive.
    """

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


class DatabaseManager:
    """
    Manages the new library database connection and schema preparation
    for the Track domain and V5 AI modules.
    """
    
    def __init__(self, db_path: Path = LIBRARY_DB_PATH):
        self.db_path = db_path
        self._initialize_schema()
        self._run_migrations()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a configured SQLite connection."""
        conn = sqlite3.connect(
            str(self.db_path), timeout=_BUSY_TIMEOUT_S, factory=_ClosingConnection
        )
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL: los lectores no bloquean al escritor ni al revés. Es persistente
        # en el archivo, así que después de la primera vez es un no-op.
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _initialize_schema(self):
        """
        Creates the tables required for WaveLoad V5.
        This prepares the schema for Track models, assets, and future AI features.
        """
        schema_sql = """
        -- 1. Tracks Table
        CREATE TABLE IF NOT EXISTS tracks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT,
            album TEXT,
            duration INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- 2. Track Assets Table
        CREATE TABLE IF NOT EXISTS track_assets (
            id TEXT PRIMARY KEY,
            track_id TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE
        );

        -- 3. Track Analysis Table (Future AI Readiness)
        CREATE TABLE IF NOT EXISTS track_analysis (
            track_id TEXT PRIMARY KEY,
            bpm REAL,
            musical_key TEXT,
            energy_level REAL,
            analyzed_at TEXT,
            FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE
        );

        -- 4. Track Embeddings Table (Future AI Readiness)
        CREATE TABLE IF NOT EXISTS track_embeddings (
            track_id TEXT PRIMARY KEY,
            embedding_vector BLOB NOT NULL,
            model_version TEXT NOT NULL,
            FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE
        );

        -- 5. Compatibility Cache Table (Future AI Readiness)
        CREATE TABLE IF NOT EXISTS compatibility_cache (
            track_id_a TEXT NOT NULL,
            track_id_b TEXT NOT NULL,
            compatibility_score REAL NOT NULL,
            computed_at TEXT NOT NULL,
            PRIMARY KEY (track_id_a, track_id_b),
            FOREIGN KEY (track_id_a) REFERENCES tracks (id) ON DELETE CASCADE,
            FOREIGN KEY (track_id_b) REFERENCES tracks (id) ON DELETE CASCADE
        );
        """
        
        try:
            with self.get_connection() as conn:
                conn.executescript(schema_sql)
                conn.commit()
            logger.info("Library database schema initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database schema: {e}")

    def _run_migrations(self):
        """
        Runs idempotent, transactional migrations on every startup.
        Each migration checks whether it has already been applied before executing.
        Safe to run multiple times — no data loss on repeated execution.
        """
        try:
            with self.get_connection() as conn:
                self._migrate_source_metadata_columns(conn)
                self._migrate_deduplicate_and_unique_constraint(conn)
                self._migrate_collections_schema(conn)
                conn.commit()
                logger.info("Database migrations completed successfully.")
        except Exception as e:
            logger.error(f"Database migration failed: {e}")
            # Do not raise — the application should still start with the existing schema

    def _migrate_source_metadata_columns(self, conn: sqlite3.Connection):
        """Migration: Add source_* columns to tracks table for Collection preparation."""
        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(tracks)").fetchall()}
        
        new_columns = [
            ("source_platform", "TEXT"),
            ("source_playlist_name", "TEXT"),
            ("source_playlist_id", "TEXT"),
            ("source_url", "TEXT"),
        ]
        
        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                conn.execute(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}")
                logger.info(f"Migration: Added column '{col_name}' to tracks table.")

    def _migrate_deduplicate_and_unique_constraint(self, conn: sqlite3.Connection):
        """Migration: Deduplicate track_assets by file_path and add UNIQUE index."""
        # Check if the UNIQUE index already exists (migration already applied)
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='track_assets'"
        ).fetchall()
        index_names = {row[0] for row in indexes}
        
        if "idx_track_assets_file_path_unique" in index_names:
            return  # Already migrated
        
        # Count duplicates before cleanup
        dup_count = conn.execute(
            "SELECT COUNT(*) FROM (SELECT file_path FROM track_assets GROUP BY file_path HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        
        if dup_count > 0:
            logger.info(f"Migration: Found {dup_count} duplicate file_paths. Deduplicating...")
            
            # For each duplicate file_path group, keep the asset with the smallest rowid
            # (earliest inserted). Delete the rest.
            conn.execute("""
                DELETE FROM track_assets 
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM track_assets GROUP BY file_path
                )
            """)
            
            # Remove orphaned tracks (tracks that no longer have any assets)
            orphan_count = conn.execute("""
                SELECT COUNT(*) FROM tracks 
                WHERE id NOT IN (SELECT DISTINCT track_id FROM track_assets)
            """).fetchone()[0]
            
            conn.execute("""
                DELETE FROM tracks 
                WHERE id NOT IN (SELECT DISTINCT track_id FROM track_assets)
            """)
            
            logger.info(f"Migration: Removed {dup_count} duplicate assets and {orphan_count} orphaned tracks.")
        
        # Now add the UNIQUE index to prevent future duplicates at the database level
        conn.execute(
            "CREATE UNIQUE INDEX idx_track_assets_file_path_unique ON track_assets(file_path)"
        )
        logger.info("Migration: Added UNIQUE index on track_assets.file_path.")


    def _migrate_collections_schema(self, conn: sqlite3.Connection):
        """Migration: create the Collections engine schema (tags + queries).

        Adds the six tables of the tag/query engine plus their indexes. It is
        idempotent by construction (every statement is ``IF NOT EXISTS``) and
        purely additive: it never reads, rewrites or deletes a single row of
        the existing library. Running it on a database that already has the
        tables is a no-op.

        Naming is frozen here on purpose: once this runs against the real
        library, renaming a table or column costs a data migration.
        """
        collections_sql = """
        -- Vocabulario de tags. Un tag es siempre namespace:value.
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (namespace, value)
        );

        -- Asignación de un tag a un track, con su procedencia.
        -- PK compuesta con source: el mismo tag puede venir de dos fuentes a la
        -- vez (manual + ai) y coexisten sin pisarse.
        CREATE TABLE IF NOT EXISTS track_tags (
            track_id TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (track_id, tag_id, source),
            FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
        );

        -- Smart collection: pila ordenada de capas. Se re-evalúa siempre.
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_json TEXT,
            limit_n INTEGER,
            ast_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        -- Una capa de la pila. El predicado va como AST en JSON, nunca texto.
        CREATE TABLE IF NOT EXISTS collection_layers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            mode TEXT NOT NULL,
            ast_json TEXT NOT NULL,
            FOREIGN KEY (collection_id) REFERENCES collections (id) ON DELETE CASCADE
        );

        -- Crate: colección manual, lista ordenada y fija de tracks.
        CREATE TABLE IF NOT EXISTS crates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS crate_entries (
            crate_id INTEGER NOT NULL,
            track_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            PRIMARY KEY (crate_id, track_id),
            FOREIGN KEY (crate_id) REFERENCES crates (id) ON DELETE CASCADE,
            FOREIGN KEY (track_id) REFERENCES tracks (id) ON DELETE CASCADE
        );

        -- Índices del motor de queries. track_tags se recorre en los dos
        -- sentidos: por tag (¿quiénes tienen este tag?) y por track (¿qué tags
        -- tiene este track?).
        CREATE INDEX IF NOT EXISTS idx_track_tags_tag ON track_tags (tag_id, track_id);
        CREATE INDEX IF NOT EXISTS idx_track_tags_track ON track_tags (track_id);
        CREATE INDEX IF NOT EXISTS idx_track_tags_source ON track_tags (source);
        CREATE INDEX IF NOT EXISTS idx_tags_namespace ON tags (namespace);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_layers_position
            ON collection_layers (collection_id, position);
        CREATE INDEX IF NOT EXISTS idx_crate_entries_crate
            ON crate_entries (crate_id, position);

        -- Los nodos range/compare del AST pegan contra estas columnas.
        CREATE INDEX IF NOT EXISTS idx_track_analysis_bpm ON track_analysis (bpm);
        CREATE INDEX IF NOT EXISTS idx_track_analysis_energy ON track_analysis (energy_level);
        """

        existing = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.executescript(collections_sql)

        created = {
            "tags", "track_tags", "collections",
            "collection_layers", "crates", "crate_entries",
        } - existing
        if created:
            logger.info(
                "Migration: Collections schema created (%s).",
                ", ".join(sorted(created)),
            )


# --- Instancia global, perezosa ------------------------------------------------
# Construir un DatabaseManager corre las migraciones. Antes esto pasaba al
# *importar* el módulo, así que cualquier import (un test, una herramienta de
# línea de comandos) tocaba la base real del usuario como efecto colateral.
# Ahora se construye en el primer uso; el nombre ``db_manager`` sigue existiendo
# vía PEP 562 para no romper a quien lo importa directo.
_db_manager: "DatabaseManager | None" = None


def get_db_manager() -> DatabaseManager:
    """Devuelve el DatabaseManager de la librería real, construyéndolo una vez."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def __getattr__(name: str):
    if name == "db_manager":
        return get_db_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
