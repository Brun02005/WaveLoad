"""Genera una librería sintética para medir el motor de queries a escala.

No toca la librería real: escribe una base nueva en la ruta que se le indique.
Los datos imitan la distribución de la librería real (techno-centrada: la
mayoría de los tracks entre 120 y 140 BPM), porque una distribución uniforme
haría los filtros artificialmente selectivos y la medición, optimista.

Uso:
    python tools/make_synthetic_library.py --tracks 50000 --out bench50k.db
"""

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.database import DatabaseManager  # noqa: E402
from services.tagging_service import TaggingService  # noqa: E402
from storage.tag_repository import SqliteTagRepository  # noqa: E402

PLATAFORMAS = ["local"] * 8 + ["youtube"] * 3 + ["soundcloud"]
GENEROS = ["techno", "minimal", "house", "deep-house", "trance", "drum-bass", "ambient"]
MOODS = ["dark", "euphoric", "hypnotic", "melancholic", "aggressive"]
CONTEXTOS = ["warmup", "peak-time", "closing", "afterhours"]
PALABRAS = ["Dark", "Night", "Machine", "Pulse", "Echo", "Drift", "Signal", "Void",
            "Neon", "Static", "Orbit", "Ritual", "Vapor", "Iron", "Solar"]


def _bpm(rng: random.Random) -> float:
    # 60% en 120-129, 25% en 130-139, el resto disperso: la forma real.
    dado = rng.random()
    if dado < 0.60:
        return round(rng.uniform(120, 130), 1)
    if dado < 0.85:
        return round(rng.uniform(130, 140), 1)
    if dado < 0.95:
        return round(rng.uniform(140, 160), 1)
    return round(rng.uniform(85, 120), 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracks", type=int, default=50000)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()

    if args.out.exists():
        print(f"{args.out} ya existe. Borralo o elegí otra ruta.")
        return 1

    rng = random.Random(args.seed)
    db = DatabaseManager(db_path=args.out)
    repo = SqliteTagRepository(db=db)

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    claves = [f"{n}{letra}" for n in range(1, 13) for letra in ("A", "B")]

    print(f"Generando {args.tracks} tracks en {args.out.name}...")
    conn = db.get_connection()
    try:
        for i in range(args.tracks):
            track_id = str(uuid.uuid4())
            titulo = f"{rng.choice(PALABRAS)} {rng.choice(PALABRAS)} {i}"
            creado = (base + timedelta(minutes=i)).isoformat()
            conn.execute(
                "INSERT INTO tracks (id, title, artist, album, duration, created_at,"
                " updated_at, source_platform, source_playlist_name) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    track_id,
                    titulo,
                    f"Artista {i % 900}",
                    f"Album {i % 300}",
                    rng.randint(150, 600),
                    creado,
                    creado,
                    rng.choice(PLATAFORMAS),
                    f"Playlist {i % 40}" if rng.random() < 0.3 else None,
                ),
            )
            # 97% analizados, igual que la librería real (781 de 784).
            if rng.random() < 0.97:
                conn.execute(
                    "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                    " analyzed_at) VALUES (?,?,?,?,?)",
                    (track_id, _bpm(rng), rng.choice(claves),
                     float(rng.randint(1, 10)), creado),
                )
            if i and i % 10000 == 0:
                print(f"  {i}...")
        conn.commit()
    finally:
        conn.close()

    print("Derivando tags...")
    service = TaggingService(repo)
    print(f"  derived   -> {service.backfill_derived()}")
    print(f"  inherited -> {service.backfill_inherited()}")

    print("Agregando tags manuales (género, mood, contexto)...")
    conn = db.get_connection()
    try:
        ids = [r[0] for r in conn.execute("SELECT id FROM tracks")]
        for track_id in ids:
            manuales = [("genre", rng.choice(GENEROS))]
            if rng.random() < 0.6:
                manuales.append(("mood", rng.choice(MOODS)))
            if rng.random() < 0.35:
                manuales.append(("context", rng.choice(CONTEXTOS)))
            for namespace, valor in manuales:
                from domain.tags import Tag, TagSource
                tag_id = repo.get_or_create_tag_id(Tag(namespace, valor), conn)
                conn.execute(
                    "INSERT OR IGNORE INTO track_tags (track_id, tag_id, source,"
                    " confidence, created_at) VALUES (?,?,?,?,?)",
                    (track_id, tag_id, TagSource.MANUAL.value, 1.0, base.isoformat()),
                )
        conn.commit()
        print(f"Total de asignaciones: "
              f"{conn.execute('SELECT COUNT(*) FROM track_tags').fetchone()[0]}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
