"""Mide la latencia de evaluación de predicados sobre la librería real.

Sólo lee: abre la base en modo lectura y no escribe una sola fila.

Uso:
    python tools/bench_queries.py
    python tools/bench_queries.py --db otra.db --repeats 20
"""

import argparse
import sqlite3
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.query_ast import and_, compare, not_, or_, range_, source, tag, tag_any, text  # noqa: E402
from infrastructure.database import LIBRARY_DB_PATH  # noqa: E402
from services.query_compiler import build_count_query, build_track_ids_query  # noqa: E402

CASOS = [
    ("un tag derivado", tag("bpm", "120-129")),
    ("tag_any sobre un namespace", tag_any("key")),
    ("rango de bpm", range_("bpm", 122, 128)),
    ("texto contains sobre title", text("title", "remix")),
    ("plataforma de origen", source("source_platform", "local")),
    ("dos tags en AND", and_(tag("bpm", "120-129"), tag("energy", "high"))),
    ("cuatro claves en OR", or_(*[tag("key", k) for k in ("8a", "6a", "4a", "1a")])),
    (
        "la pila de ARQUITECTURA 4.3",
        and_(
            or_(tag("key", "8a"), tag("key", "6a")),
            range_("bpm", 122, 128),
            not_(tag("context", "already-played")),
        ),
    ),
    (
        "predicado hostil: 8 tags en OR + rango + 2 negaciones",
        and_(
            or_(*[tag("key", f"{n}a") for n in range(1, 9)]),
            range_("bpm", 110, 150),
            not_(tag("energy", "low")),
            not_(source("source_platform", "youtube")),
            compare("duration", "gt", 60),
        ),
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=LIBRARY_DB_PATH)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()

    if not args.db.exists():
        print(f"No existe la base {args.db}")
        return 1

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        tracks = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        assignments = conn.execute("SELECT COUNT(*) FROM track_tags").fetchone()[0]
        print(f"Base: {args.db.name} — {tracks} tracks, {assignments} asignaciones de tag")
        print(f"{args.repeats} corridas por caso, se reporta la mediana y el peor caso.\n")
        print(f"{'caso':<52} {'filas':>6} {'mediana':>9} {'peor':>9}")
        print("-" * 80)

        peor_global = 0.0
        for nombre, nodo in CASOS:
            count_q = build_count_query(nodo)
            ids_q = build_track_ids_query(nodo)
            filas = conn.execute(count_q.sql, count_q.params).fetchone()[0]

            tiempos = []
            for _ in range(args.repeats):
                inicio = time.perf_counter()
                conn.execute(ids_q.sql, ids_q.params).fetchall()
                tiempos.append((time.perf_counter() - inicio) * 1000)

            mediana, peor = statistics.median(tiempos), max(tiempos)
            peor_global = max(peor_global, peor)
            print(f"{nombre:<52} {filas:>6} {mediana:>7.2f}ms {peor:>7.2f}ms")

        print("-" * 80)
        print(f"Peor caso de toda la corrida: {peor_global:.2f} ms sobre {tracks} tracks.")
        if tracks:
            if tracks < 50000:
                proyectado = peor_global * 50000 / tracks
                print(
                    f"Extrapolación lineal ingenua a 50.000 tracks: ~{proyectado:.0f} ms. "
                    "Es una cota grosera y en la práctica pesimista: medido sobre una "
                    "librería sintética de 50.000 tracks, el peor caso real da bastante "
                    "menos. Generala con tools/make_synthetic_library.py."
                )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
