"""
services/compatibility_service.py
=================================
Deterministic harmonic + tempo compatibility between library tracks, following
the Camelot wheel mixing rules used by DJs. Pure (Qt-free) so it can be tested
headlessly and reused anywhere.

Camelot rules (target key = number N + letter L):
  * same code (N,L)         -> perfect harmonic match          (cat 0)
  * same N, other letter    -> relative major/minor            (cat 1)
  * N+1, same letter        -> one step up the wheel           (cat 2)
  * N-1, same letter        -> one step down the wheel         (cat 3)
  * N+2, same letter        -> energy boost (common in sets)   (cat 4)
  * N+7, same letter        -> "Subidón": +1 semitone key lift (cat 5)
Results are interleaved across these categories (round-robin) so a big cluster
of same-key tracks never hides the relative/adjacent options — you always see a
mix to build a whole set from. The +7 "Subidón" is an aggressive peak-time key
change, so it sits last in each round. BPM must be within a pitch-mixable window
(default ±12%); half/double-time matches are also surfaced.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

BPM_TOLERANCE = 0.12  # ±12% — a wide, generous pitch-mixing range


@dataclass(frozen=True)
class CompatibleTrack:
    id: str
    title: str
    artist: str
    key_camelot: str
    bpm: Optional[float]
    relation: str      # human label, e.g. "Perfecta", "Relativa", "Subir energía"
    bpm_delta: float   # candidate_bpm - target_bpm (0 if unknown)
    category: int      # 0..4 harmonic-relation category (see module docstring)


def _parse_camelot(code: Any):
    if not code or code in ("—", ""):
        return None
    code = str(code).strip().upper()
    letter = code[-1]
    if letter not in ("A", "B"):
        return None
    try:
        number = int(code[:-1])
    except ValueError:
        return None
    if not 1 <= number <= 12:
        return None
    return number, letter


def _parse_bpm(value: Any) -> Optional[float]:
    if value in (None, "—", ""):
        return None
    try:
        return float(str(value))
    except (ValueError, TypeError):
        return None


def _wheel_step(n: int, delta: int) -> int:
    """Camelot number arithmetic on the 1..12 ring."""
    return (n - 1 + delta) % 12 + 1


def harmonic_relation(key_a: Any, key_b: Any):
    """Public helper: harmonic relation between two Camelot codes.

    Returns (label, category) if compatible, else None. Used by the graph's
    similarity engine to score/gate edges.
    """
    ka, kb = _parse_camelot(key_a), _parse_camelot(key_b)
    if ka is None or kb is None:
        return None
    return _relation(ka, kb)


def _relation(target, cand):
    """Return (label, category) if harmonically compatible, else None."""
    tn, tl = target
    cn, cl = cand
    if tn == cn and tl == cl:
        return "Perfecta", 0
    if tn == cn and tl != cl:
        return "Relativa", 1
    if tl == cl and cn == _wheel_step(tn, +1):
        return "Subir energía", 2
    if tl == cl and cn == _wheel_step(tn, -1):
        return "Bajar energía", 3
    if tl == cl and cn == _wheel_step(tn, +2):
        return "Impulso energía", 4
    if tl == cl and cn == _wheel_step(tn, +7):
        return "Subidón (semitono)", 5
    return None


def _bpm_relation(target_bpm: Optional[float], cand_bpm: Optional[float]):
    """Return (label_suffix, delta, ok) for tempo compatibility."""
    if target_bpm is None or cand_bpm is None:
        return "", 0.0, True  # unknown tempo: don't exclude, just no delta
    delta = cand_bpm - target_bpm
    if abs(delta) <= target_bpm * BPM_TOLERANCE:
        return "", delta, True
    # half / double time (e.g. 128 mixes with 64 or 174-drum'n'bass halves)
    for factor in (2.0, 0.5):
        if abs(cand_bpm - target_bpm * factor) <= target_bpm * factor * BPM_TOLERANCE:
            return ("doble tiempo" if factor == 2.0 else "mitad tiempo"), delta, True
    return "", delta, False


class CompatibilityService:
    @staticmethod
    def find_compatible(target: Dict[str, Any], candidates: List[Dict[str, Any]],
                        max_results: int = 24) -> List[CompatibleTrack]:
        """Find library tracks that mix harmonically + tempo-wise with `target`.

        `target` and `candidates` are presentation dicts (id, title, artist,
        key, bpm). Returns up to `max_results` CompatibleTracks, interleaved
        across harmonic categories so every mixing option (relative, adjacent,
        energy moves) is represented rather than being buried under same-key hits.
        """
        t_key = _parse_camelot(target.get("key"))
        if t_key is None:
            return []
        t_bpm = _parse_bpm(target.get("bpm"))
        t_id = target.get("id")

        # 6 buckets, one per harmonic category (see _relation).
        buckets: List[List[CompatibleTrack]] = [[], [], [], [], [], []]
        for cand in candidates:
            if cand.get("id") == t_id:
                continue
            c_key = _parse_camelot(cand.get("key"))
            if c_key is None:
                continue
            rel = _relation(t_key, c_key)
            if rel is None:
                continue
            label, category = rel
            c_bpm = _parse_bpm(cand.get("bpm"))
            suffix, delta, bpm_ok = _bpm_relation(t_bpm, c_bpm)
            if not bpm_ok:
                continue
            if suffix:
                label = f"{label} · {suffix}"
            buckets[category].append(CompatibleTrack(
                id=str(cand.get("id", "")),
                title=cand.get("title", "—"),
                artist=cand.get("artist", "—"),
                key_camelot=str(cand.get("key", "—")),
                bpm=c_bpm,
                relation=label,
                bpm_delta=delta,
                category=category,
            ))

        # Best BPM match first within each category.
        for b in buckets:
            b.sort(key=lambda r: abs(r.bpm_delta))

        # Round-robin interleave across categories so variety surfaces up top.
        results: List[CompatibleTrack] = []
        idx = 0
        while len(results) < max_results and any(idx < len(b) for b in buckets):
            for b in buckets:
                if idx < len(b):
                    results.append(b[idx])
                    if len(results) >= max_results:
                        break
            idx += 1
        return results
