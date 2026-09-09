"""Backfill de tags automáticos sobre una librería existente.

Recalcula los tags `derived` (BPM, clave, energía) y `inherited` (plataforma,
playlist) de todos los tracks. Es idempotente: correrlo dos veces no cambia
nada la segunda vez, y nunca toca las asignaciones `manual`.

Uso:
    python tools/backfill_tags.py --dry-run
    python tools/backfill_tags.py --db waveload_library.backup.db
    python tools/backfill_tags.py
"""

import argparse
import gc
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.tags import TagSource  # noqa: E402
from infrastructure.database import DatabaseManager, LIBRARY_DB_PATH  # noqa: E402
from services.tagging_service import TaggingService  # noqa: E402
from storage.tag_repository import SqliteTagRepository  # noqa: E402


def _backup(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = db_path.with_name(f"{db_path.stem}.pre-backfill-{stamp}.db")
    shutil.copy2(db_path, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=LIBRARY_DB_PATH,
                        help="Ruta de la librería (por defecto, la real).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Corre sobre una copia descartable y no toca la base.")
    parser.add_argument("--no-backup", action="store_true",
                        help="No copiar la base antes de escribir. Usalo sólo sobre copias.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    db_path: Path = args.db
    if not db_path.exists():
        print(f"No existe la base {db_path}")
        return 1

    if args.dry_run:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        db_path = db_path.with_name(f"{args.db.stem}.dryrun-{stamp}.db")
        shutil.copy2(args.db, db_path)
        print(f"Dry-run sobre una copia: {db_path.name}")
    elif not args.no_backup:
        print(f"Backup: {_backup(db_path).name}")

    repo = SqliteTagRepository(db=DatabaseManager(db_path=db_path))
    service = TaggingService(repo)

    print(f"\nBase: {db_path.name}")
    print(f"Asignaciones antes: {repo.count_assignments()}")

    derived = service.backfill_derived()
    print(f"  derived   -> {derived}")
    inherited = service.backfill_inherited()
    print(f"  inherited -> {inherited}")

    print(f"\nAsignaciones después: {repo.count_assignments()}")
    print(f"  manual={repo.count_assignments(TagSource.MANUAL)}"
          f" derived={repo.count_assignments(TagSource.DERIVED)}"
          f" inherited={repo.count_assignments(TagSource.INHERITED)}")
    print(f"Vocabulario por namespace: {repo.count_by_namespace()}")

    for report in (derived, inherited):
        for error in report.errors[:10]:
            print(f"  error: {error}")

    if args.dry_run:
        # Las conexiones se cierran al recolectarse (el repositorio usa el
        # `with conn` de sqlite3, que hace commit pero no cierra). Sin esto
        # Windows no deja borrar el archivo.
        del repo, service
        gc.collect()
        try:
            db_path.unlink()
            print("\nCopia de dry-run borrada. La base real no se tocó.")
        except OSError as exc:
            print(f"\nLa base real no se tocó. Queda {db_path.name} sin borrar: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
