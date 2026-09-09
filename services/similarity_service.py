"""
services/similarity_service.py
==============================
Deterministic transition-similarity engine for the Music Knowledge Graph.

Scores how well two tracks transition (0..100) from the data we actually have —
BPM, Camelot key and energy — using configurable weights. The prompt's full
weight set also lists genre / danceability / DJ-history; those dimensions don't
exist yet, so their weight is 0 and the available weights are renormalised.
Everything is pure/Qt-free and testable.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from services.compatibility_service import harmonic_relation, _parse_bpm

# Intended weights (prompt spec). Dimensions we can't measure yet stay at 0 and
# the rest are renormalised so the score is always 0..100.
DEFAULT_WEIGHTS = {
    "bpm": 0.35,
    "key": 0.25,
    "energy": 0.15,
    "genre": 0.0,        # not available yet
    "danceability": 0.0, # not available yet
    "history": 0.0,      # not available yet
}

# Camelot relation category -> harmonic closeness (0..1). Categories come from
# compatibility_service._relation: 0 same, 1 relative, 2 up, 3 down, 4 boost, 5 subidón.
_KEY_SCORE = {0: 1.0, 1: 0.9, 2: 0.85, 3: 0.85, 4: 0.6, 5: 0.5}

BPM_TOLERANCE = 0.12  # matches the compatibility window


@dataclass(frozen=True)
class TransitionScore:
    score: int                 # 0..100
    label: str                 # "Excelente" / "Buena" / "Aceptable" / "Débil"
    relation: Optional[str]    # Camelot relation label, or None
    bpm_delta: float
    reasons: list = field(default_factory=list)  # short explanation chips

    @property
    def compatible(self) -> bool:
        return self.relation is not None


class SimilarityEngine:
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)

    def _bpm_component(self, a: Optional[float], b: Optional[float]):
        if a is None or b is None:
            return 0.5, 0.0  # neutral if unknown
        delta = b - a
        rel = abs(delta) / a if a else 1.0
        score = max(0.0, 1.0 - rel / BPM_TOLERANCE)  # 1 at same tempo -> 0 at ±tol
        return score, delta

    def score(self, a: Dict[str, Any], b: Dict[str, Any]) -> TransitionScore:
        """Transition score from track `a` into track `b` (presentation dicts)."""
        rel = harmonic_relation(a.get("key"), b.get("key"))
        key_label = rel[0] if rel else None
        key_score = _KEY_SCORE.get(rel[1], 0.0) if rel else 0.0

        a_bpm, b_bpm = _parse_bpm(a.get("bpm")), _parse_bpm(b.get("bpm"))
        bpm_score, bpm_delta = self._bpm_component(a_bpm, b_bpm)

        ae, be = a.get("energy"), b.get("energy")
        if ae is None or be is None:
            energy_score, e_delta = 0.5, None
        else:
            e_delta = int(be) - int(ae)
            energy_score = max(0.0, 1.0 - abs(e_delta) / 5.0)

        w = self.weights
        active = w["bpm"] + w["key"] + w["energy"]  # renormalise available dims
        if active <= 0:
            active = 1.0
        raw = (w["bpm"] * bpm_score + w["key"] * key_score + w["energy"] * energy_score) / active
        score = int(round(raw * 100))

        reasons = []
        if abs(bpm_delta) < 1.0:
            reasons.append("BPM idéntico")
        elif bpm_score >= 0.6:
            reasons.append("Drift de BPM mínimo")
        if key_label:
            reasons.append(key_label)
        if e_delta is not None:
            if e_delta == 0:
                reasons.append("Energía igual")
            elif e_delta > 0:
                reasons.append(f"Sube energía +{e_delta}")
            else:
                reasons.append(f"Baja energía {e_delta}")

        if score >= 90:
            label = "Excelente"
        elif score >= 75:
            label = "Buena"
        elif score >= 60:
            label = "Aceptable"
        else:
            label = "Débil"

        return TransitionScore(
            score=score, label=label, relation=key_label,
            bpm_delta=bpm_delta, reasons=reasons,
        )
