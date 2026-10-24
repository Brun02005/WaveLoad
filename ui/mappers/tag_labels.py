"""
ui/mappers/tag_labels.py
========================
Cómo se muestra un tag. La identidad es el slug (``peak-time``,
``drum-bass``); acá está la versión que lee el usuario y las sugerencias que se
ofrecen al etiquetar.

Es presentación pura: cambiar una etiqueta de acá no cambia ningún dato.
"""

from domain.tags import NS_CONTEXT, NS_GENRE, NS_MOOD, NS_STATUS

# Los ejes que el usuario edita, en el orden en que se muestran.
EDITABLE_NAMESPACES = (NS_GENRE, NS_MOOD, NS_CONTEXT, NS_STATUS)

NAMESPACE_TITLES = {
    NS_GENRE: "Género",
    NS_MOOD: "Mood",
    NS_CONTEXT: "Momento del set",
    NS_STATUS: "Estado",
}

NAMESPACE_HINTS = {
    NS_GENRE: "Qué es: house, techno, reggaetón…",
    NS_MOOD: "Cómo se siente: oscuro, eufórico, hipnótico…",
    NS_CONTEXT: "Cuándo entra en la noche",
    NS_STATUS: "En qué punto de tu curaduría está",
}

# Sugerencias cuando la librería todavía no tiene valores propios en ese eje.
# Momento y estado son vocabularios cortos y fijos en la práctica; género y
# mood se completan con lo que el usuario vaya escribiendo.
SUGGESTIONS = {
    NS_GENRE: [
        "house", "tech-house", "deep-house", "afro-house", "melodic-house-techno",
        "progressive-house", "techno", "minimal", "disco", "nu-disco", "drum-bass",
        "trance", "reggaeton", "cumbia", "dembow", "pop", "hip-hop", "electronic",
    ],
    NS_MOOD: ["dark", "euphoric", "hypnotic", "groovy", "melancholic", "energetic", "chill", "sexy"],
    NS_CONTEXT: ["opening", "warmup", "peak-time", "closing", "afterhours"],
    NS_STATUS: ["ready", "to-review", "already-played"],
}

# Etiquetas en castellano para los valores que no se leen bien desde el slug.
_LABELS = {
    (NS_CONTEXT, "opening"): "Apertura",
    (NS_CONTEXT, "warmup"): "Warm-up",
    (NS_CONTEXT, "peak-time"): "Peak time",
    (NS_CONTEXT, "closing"): "Cierre",
    (NS_CONTEXT, "afterhours"): "After",
    (NS_STATUS, "ready"): "Lista para tocar",
    (NS_STATUS, "to-review"): "Para revisar",
    (NS_STATUS, "already-played"): "Ya la toqué",
    (NS_MOOD, "dark"): "Oscuro",
    (NS_MOOD, "euphoric"): "Eufórico",
    (NS_MOOD, "hypnotic"): "Hipnótico",
    (NS_MOOD, "groovy"): "Groovy",
    (NS_MOOD, "melancholic"): "Melancólico",
    (NS_MOOD, "energetic"): "Enérgico",
    (NS_MOOD, "chill"): "Tranqui",
    (NS_MOOD, "sexy"): "Sexy",
    (NS_GENRE, "drum-bass"): "Drum & Bass",
    (NS_GENRE, "melodic-house-techno"): "Melodic House & Techno",
    (NS_GENRE, "r-b"): "R&B",
    (NS_GENRE, "hip-hop"): "Hip Hop",
    (NS_GENRE, "edm"): "EDM",
    (NS_GENRE, "nu-disco"): "Nu Disco",
    (NS_GENRE, "reggaeton"): "Reggaetón",
    (NS_GENRE, "electronic"): "Electrónica",
}


def tag_label(namespace: str, value: str) -> str:
    """``("context", "peak-time")`` -> ``"Peak time"``; un valor sin etiqueta
    propia se muestra desde el slug: ``"tech-house"`` -> ``"Tech House"``."""
    etiqueta = _LABELS.get((namespace, value))
    if etiqueta:
        return etiqueta
    return " ".join(p.capitalize() if not p.isupper() else p for p in value.split("-"))
