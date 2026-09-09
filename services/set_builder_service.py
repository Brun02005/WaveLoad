"""
services/set_builder_service.py
===============================
Auto-sequences a curated set into a play order that jointly optimises
transition quality (harmonic + tempo, via SimilarityEngine) and adherence to an
event-specific energy curve. Pure/Qt-free and testable.

Objective maximised over an ordering:
    mean_transition_value  −  λ · mean_squared_energy_deviation·100

Transition value uses the SimilarityEngine score, penalised when two tracks are
not harmonically compatible. The energy curve is a per-event target shape that
the set's (relatively normalised) energies are fitted to. A greedy pass seeds a
good order; a 2-opt pass polishes it to the best order found.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.similarity_service import SimilarityEngine
from services.compatibility_service import _parse_camelot, _parse_bpm

# UI labels for the presets.
EVENT_PRESETS = {
    "warmup": "Warm-up",
    "club": "Club prime-time",
    "festival": "Festival",
    "afterhours": "Afterhours",
}

_DEFAULT_LAMBDA = 0.6
_BPM_JUMP_WARN = 8.0
_ENERGY_DROP_WARN = -4


def interp_curve(points, t: float) -> float:
    """Linearly interpolate a custom energy curve given by evenly-spaced control
    points (each 0..1) at position t∈[0,1]."""
    if not points:
        return 0.5
    if len(points) == 1:
        return float(points[0])
    t = max(0.0, min(1.0, t))
    x = t * (len(points) - 1)
    i = int(x)
    if i >= len(points) - 1:
        return float(points[-1])
    frac = x - i
    return float(points[i]) * (1 - frac) + float(points[i + 1]) * frac


def energy_target(event: str, t: float) -> float:
    """Target *relative* energy (0..1) at position t∈[0,1] for an event."""
    t = max(0.0, min(1.0, t))
    if event == "warmup":
        return 0.20 + 0.40 * t                      # low, slowly rising
    if event == "festival":
        return max(0.5, min(1.0, 0.72 + 0.26 * math.sin(2 * math.pi * 1.5 * t)))  # high, wavy
    if event == "afterhours":
        return 0.72 - 0.42 * t                       # descends, hypnotic
    # club (default): build to a held peak near ~82%, then ease slightly
    peak = 0.82
    if t <= peak:
        return 0.30 + (0.92 - 0.30) * (t / peak)
    return 0.92 - 0.12 * ((t - peak) / (1 - peak))


@dataclass
class SetStep:
    track: Dict[str, Any]
    transition_score: int          # mix quality into this track (0 for the opener)
    relation: Optional[str]        # Camelot relation from the previous track
    bpm_delta: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class GeneratedSet:
    steps: List[SetStep]
    avg_quality: int               # mean transition score across the set
    curve_fit: int                 # 0..100 how well energy follows the event curve
    event: str


class SetBuilderService:
    def __init__(self, weights=None):
        self.engine = SimilarityEngine(weights)

    @staticmethod
    def analyzable(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [t for t in tracks
                if _parse_camelot(t.get("key")) and _parse_bpm(t.get("bpm")) is not None]

    def build_set(self, tracks: List[Dict[str, Any]], event: str = "club",
                  lam: float = _DEFAULT_LAMBDA,
                  anchors: Optional[Dict[str, str]] = None,
                  curve_points: Optional[List[float]] = None) -> GeneratedSet:
        """Optimise a play order. `anchors` pins tracks by role: {'start': id,
        'end': id, 'peak': id} — those positions stay fixed during optimisation.
        `curve_points` (from the Journey Designer) overrides the event's energy
        curve with a custom one."""
        curve_fn = ((lambda tt: interp_curve(curve_points, tt)) if curve_points
                    else (lambda tt: energy_target(event, tt)))
        tracks = self.analyzable(tracks)
        n = len(tracks)
        if n == 0:
            return GeneratedSet([], 0, 0, event)
        if n == 1:
            return GeneratedSet([SetStep(tracks[0], 0, None, 0.0, [])], 0, 100, event)

        anchors = anchors or {}
        id_to_idx = {t["id"]: i for i, t in enumerate(tracks)}
        # Map anchor roles to fixed (position -> track index).
        fixed: Dict[int, int] = {}
        if anchors.get("start") in id_to_idx:
            fixed[0] = id_to_idx[anchors["start"]]
        if anchors.get("end") in id_to_idx:
            fixed[n - 1] = id_to_idx[anchors["end"]]
        if anchors.get("peak") in id_to_idx:
            peak_pos = max(range(n), key=lambda p: energy_target(event, p / (n - 1)))
            if peak_pos not in fixed and id_to_idx[anchors["peak"]] not in fixed.values():
                fixed[peak_pos] = id_to_idx[anchors["peak"]]

        energies = [int(t.get("energy") or 5) for t in tracks]
        emin, emax = min(energies), max(energies)
        rng = (emax - emin) or 1
        norm = [(e - emin) / rng for e in energies]

        # Precompute pairwise optimisation values (penalised transition score).
        val = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                ts = self.engine.score(tracks[i], tracks[j])
                val[i][j] = ts.score if ts.compatible else max(0, ts.score - 40)

        def target(pos: int) -> float:
            return curve_fn(pos / (n - 1))

        # Objective is a 0..1 blend: (1-λ)·transition quality + λ·energy-curve fit,
        # so λ is a real "flow ↔ curve" knob and both terms are comparable.
        def order_score(order: List[int]) -> float:
            q = (sum(val[order[k]][order[k + 1]] for k in range(len(order) - 1))
                 / (len(order) - 1)) / 100.0
            dev = sum((norm[order[i]] - target(i)) ** 2 for i in range(len(order))) / len(order)
            return (1 - lam) * q + lam * (1 - dev)

        # --- Greedy seed: fill fixed positions, then follow the curve. ---
        order: List[Optional[int]] = [None] * n
        used = set()
        for pos, idx in fixed.items():
            order[pos] = idx
            used.add(idx)
        for pos in range(n):
            if order[pos] is not None:
                continue
            tg = target(pos)
            prev = order[pos - 1] if pos > 0 and order[pos - 1] is not None else None
            nxt = max((i for i in range(n) if i not in used),
                      key=lambda c: ((1 - lam) * (val[prev][c] / 100.0) if prev is not None else 0.0)
                      + lam * (1 - (norm[c] - tg) ** 2))
            order[pos] = nxt
            used.add(nxt)

        # --- 2-opt: reverse segments while it improves the objective, never
        # disturbing a fixed (anchored) position. ---
        best, best_s = order[:], order_score(order)
        improved, guard = True, 0
        while improved and guard < 60:
            improved = False
            guard += 1
            for i in range(1, n - 1):
                for j in range(i + 1, n):
                    if any(k in fixed for k in range(i, j + 1)):
                        continue
                    cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                    s = order_score(cand)
                    if s > best_s + 1e-9:
                        best, best_s = cand, s
                        improved = True

        return self._evaluate([tracks[i] for i in best], event, curve_points)

    def _evaluate(self, ordered: List[Dict[str, Any]], event: str,
                  curve_points: Optional[List[float]] = None) -> GeneratedSet:
        """Build a GeneratedSet (per-step scores/warnings + metrics) for an
        explicit ordering — used both after optimising and for manual reorders."""
        ordered = self.analyzable(ordered)
        n = len(ordered)
        if n == 0:
            return GeneratedSet([], 0, 0, event)
        curve_fn = ((lambda tt: interp_curve(curve_points, tt)) if curve_points
                    else (lambda tt: energy_target(event, tt)))
        energies = [int(t.get("energy") or 5) for t in ordered]
        emin, emax = min(energies), max(energies)
        rng = (emax - emin) or 1

        steps: List[SetStep] = []
        scores: List[int] = []
        dev = 0.0
        for pos, t in enumerate(ordered):
            if pos == 0:
                steps.append(SetStep(t, 0, None, 0.0, []))
            else:
                ts = self.engine.score(ordered[pos - 1], t)
                warns = []
                if ts.relation is None:
                    warns.append("Choque armónico")
                if abs(ts.bpm_delta) > _BPM_JUMP_WARN:
                    warns.append(f"Salto de BPM {ts.bpm_delta:+.0f}")
                if energies[pos] - energies[pos - 1] <= _ENERGY_DROP_WARN and event != "afterhours":
                    warns.append("Caída de energía brusca")
                steps.append(SetStep(t, ts.score, ts.relation, ts.bpm_delta, warns))
                scores.append(ts.score)
            actual = (energies[pos] - emin) / rng
            dev += (actual - curve_fn(pos / (n - 1) if n > 1 else 0.0)) ** 2

        avg_q = int(round(sum(scores) / len(scores))) if scores else 0
        fit = int(round(max(0.0, 1.0 - dev / n) * 100))
        return GeneratedSet(steps, avg_q, fit, event)
