"""
tools/clean_metadata.py
========================
Recovers artist/title for tracks whose metadata is a raw ripper filename.

Preview first, then apply:

    python tools/clean_metadata.py                 # preview only, writes a report
    python tools/clean_metadata.py --apply         # apply high-confidence rows
    python tools/clean_metadata.py --apply --all   # also apply medium-confidence

Updates the library database and writes ID3 title/artist tags so DJ software
(Rekordbox, Serato, Traktor) shows the corrected names too. Files on disk are
never renamed and audio is never touched.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import BASE_DIR  # noqa: E402
from services.filename_cleaner_service import plan_cleanup  # noqa: E402

DB_PATH = BASE_DIR / "waveload_library.db"
REPORT_PATH = BASE_DIR / "limpieza_metadata_preview.txt"


def load_rows(conn):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT id, title, artist FROM tracks")]


def audio_path_for(conn, track_id):
    row = conn.execute(
        "SELECT file_path FROM track_assets WHERE track_id = ? AND asset_type LIKE 'AUDIO%' LIMIT 1",
        (track_id,),
    ).fetchone()
    return row[0] if row else None


def write_id3(path, title, artist):
    """Best-effort ID3 write. Returns True when tags were saved."""
    try:
        from mutagen.id3 import ID3, TIT2, TPE1, ID3NoHeaderError
        if not path or not Path(path).exists() or Path(path).suffix.lower() != ".mp3":
            return False
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        tags.setall("TIT2", [TIT2(encoding=3, text=title)])
        if artist:
            tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
        tags.save(path)
        return True
    except Exception as e:
        print(f"    aviso: no se pudieron escribir tags en {Path(path).name}: {e}")
        return False


def render_report(plan):
    lines = []
    for level, label in (("high", "ALTA CONFIANZA (artista + título)"),
                         ("medium", "CONFIANZA MEDIA (solo título, sin artista)")):
        rows = [p for p in plan if p["confidence"] == level]
        if not rows:
            continue
        lines.append("")
        lines.append("=" * 100)
        lines.append(f"{label} — {len(rows)} pistas")
        lines.append("=" * 100)
        for p in rows:
            lines.append(f"  ANTES : {p['old_title']}")
            artist_note = f"   | artista: {p['new_artist']}" if p["new_artist"] else ""
            year_note = f"   | año: {p['year']}" if p["year"] else ""
            lines.append(f"  DESPUÉS: {p['new_title']}{artist_note}{year_note}")
            lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Limpia metadata de nombres de archivo rippeados.")
    parser.add_argument("--apply", action="store_true", help="aplica los cambios (sin esto solo previsualiza)")
    parser.add_argument("--all", action="store_true", help="incluye también los de confianza media")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"No se encontró la base de datos en {DB_PATH}")
        return 1

    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = load_rows(conn)
        plan = plan_cleanup(rows)

        high = [p for p in plan if p["confidence"] == "high"]
        medium = [p for p in plan if p["confidence"] == "medium"]

        print(f"Biblioteca            : {len(rows)} pistas")
        print(f"Nombres a corregir    : {len(plan)}")
        print(f"  alta confianza      : {len(high)}  (recupera artista + título)")
        print(f"  confianza media     : {len(medium)}  (solo limpia el título)")

        REPORT_PATH.write_text(render_report(plan), encoding="utf-8")
        print(f"\nVista previa completa : {REPORT_PATH}")

        if not args.apply:
            print("\nNada fue modificado. Revisá el archivo de arriba.")
            print("Para aplicar solo los de alta confianza:  python tools/clean_metadata.py --apply")
            print("Para aplicar todos:                       python tools/clean_metadata.py --apply --all")
            return 0

        targets = high + medium if args.all else high
        if not targets:
            print("\nNo hay nada que aplicar.")
            return 0

        print(f"\nAplicando {len(targets)} cambios...")
        tagged = 0
        for p in targets:
            if p["new_artist"]:
                conn.execute(
                    "UPDATE tracks SET title = ?, artist = ?, updated_at = datetime('now') WHERE id = ?",
                    (p["new_title"], p["new_artist"], p["id"]),
                )
            else:
                conn.execute(
                    "UPDATE tracks SET title = ?, updated_at = datetime('now') WHERE id = ?",
                    (p["new_title"], p["id"]),
                )
            if write_id3(audio_path_for(conn, p["id"]), p["new_title"], p["new_artist"]):
                tagged += 1
        conn.commit()

        print(f"Listo. {len(targets)} pistas actualizadas en la biblioteca, {tagged} con tags ID3 reescritos.")
        if not args.all and medium:
            print(f"Quedaron {len(medium)} de confianza media sin tocar (usá --all para incluirlos).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
