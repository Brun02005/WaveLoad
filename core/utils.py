import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def clean_title(title: str) -> str:
    if not title:
        return "audio"

    patterns_to_remove = [
        r"\(Official Video\)",
        r"\(Official Music Video\)",
        r"\(Official Audio\)",
        r"\(Audio\)",
        r"\(Video\)",
        r"\(Visualizer\)",
        r"\(Lyrics\)",
        r"\(Lyric Video\)",
        r"\(HD\)",
        r"\(HQ\)",
        r"\[Official Video\]",
        r"\[Official Music Video\]",
        r"\[Official Audio\]",
        r"\[Audio\]",
        r"\[Video\]",
        r"\[Visualizer\]",
        r"\[Lyrics\]",
        r"\[Lyric Video\]",
        r"\[HD\]",
        r"\[HQ\]",
    ]

    cleaned = title
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.rstrip(".")
    return cleaned or "audio"


# Windows reserved device names (case-insensitive), which are invalid even with
# an extension appended (e.g. "CON.mp3" still fails).
_WIN_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Characters Windows/ffmpeg reject: the ASCII reserved set, ASCII control chars,
# and common full-width / look-alike variants that YouTube titles sneak in
# (e.g. the full-width pipe ｜ U+FF5C, which the old ASCII-only regex missed and
# which caused ffmpeg "Invalid argument" failures on the final .mp3 path).
_ILLEGAL_FILENAME_CHARS = re.compile(
    r'[<>:"/\\|?*]'                 # ASCII reserved
    r'|[\x00-\x1f\x7f]'             # ASCII control chars
    r'|[｜＜＞：＂／＼？＊]'  # full-width ｜＜＞：＂／＼？＊
    r'|[∣∥ǀ❘｜]'  # pipe-like look-alikes ∣ ∥ ǀ ❘
)


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """Turn an arbitrary title into a filesystem-safe base name (no extension).

    Removes reserved/illegal/control characters (including Unicode look-alikes),
    collapses whitespace, strips trailing dots/spaces (which Windows silently
    drops, causing path mismatches), avoids reserved device names, and caps the
    length so the final path stays well under the Windows MAX_PATH limit.
    """
    if not name:
        return "audio"

    # Collapse whitespace first so stray tabs/newlines become a single space
    # (rather than being deleted as control chars and merging adjacent words).
    cleaned = re.sub(r"\s+", " ", name)
    cleaned = _ILLEGAL_FILENAME_CHARS.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Windows strips trailing dots and spaces from names on disk.
    cleaned = cleaned.rstrip(". ").strip()

    if cleaned.upper() in _WIN_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(". ").strip()

    return cleaned or "audio"


def build_final_mp3_path(output_dir: Path, title: str) -> Path:
    safe_title = sanitize_filename(clean_title(title))
    return output_dir / f"{safe_title}.mp3"


def build_output_template(output_dir: Path, title: str) -> str:
    safe_title = sanitize_filename(clean_title(title))
    return str(output_dir / f"{safe_title}.%(ext)s")


def is_probable_url(text: str) -> bool:
    text = text.strip()
    return text.startswith("http://") or text.startswith("https://")


def is_supported_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        host = parsed.netloc.lower()
        return (
            "youtube.com" in host
            or "youtu.be" in host
            or "music.youtube.com" in host
        )
    except Exception:
        return False


def is_playlist_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        query = parse_qs(parsed.query)
        return "list" in query
    except Exception:
        return False


def deduplicate_urls(urls: list[str]) -> list[str]:
    seen = set()
    result = []

    for url in urls:
        key = url.strip()
        if key not in seen:
            seen.add(key)
            result.append(key)

    return result


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_YTDLP_PREFIX = re.compile(r"^(?:ERROR:\s*)?(?:\[[^\]]+\]\s*)?(?:[\w-]{6,}:\s*)?")

# (fragmento en minúsculas del error de yt-dlp, mensaje para el usuario). El
# orden importa: lo específico antes que lo genérico.
_FRIENDLY = (
    ("copyright", "Eliminado de YouTube por un reclamo de copyright."),
    ("removed by the uploader", "El autor lo eliminó."),
    ("account associated with this video has been terminated", "La cuenta que lo subió fue dada de baja."),
    ("private video", "Video privado."),
    ("members-only", "Sólo para miembros del canal."),
    ("join this channel", "Sólo para miembros del canal."),
    ("sign in to confirm your age", "Tiene restricción de edad: hace falta iniciar sesión en el navegador."),
    ("not available in your country", "No está disponible en tu país."),
    ("uploader has not made this video available", "No está disponible en tu país."),
    ("video unavailable", "El video no está disponible."),
    ("this video is unavailable", "El video no está disponible."),
    ("this video is not available", "El video no está disponible."),
    ("is not available", "El video no está disponible."),
    ("unsupported url", "Enlace no soportado."),
    ("http error 403", "YouTube rechazó la descarga (403). Probá activar las cookies del navegador."),
    ("http error 404", "El video no existe (404)."),
    ("http error 429", "YouTube está limitando las descargas. Esperá unos minutos."),
    ("connection broken", "Se cortó la conexión. Probá de nuevo."),
    ("timed out", "La conexión tardó demasiado. Probá de nuevo."),
    ("getaddrinfo failed", "Sin conexión a internet."),
    ("unable to download", "No se pudo descargar el video."),
    ("ffmpeg", "FFmpeg no está instalado o no está en el PATH."),
    ("cancelada por el usuario", "Cancelada por el usuario."),
)


def friendly_error_message(error_text: str) -> str:
    """El error de yt-dlp o FFmpeg en una frase que entiende un usuario.

    yt-dlp mete códigos de color de terminal (``[0;31m``) y prefijos como
    ``ERROR: [youtube] qruvRVkz_WQ:`` que en la interfaz sólo son ruido. Un error
    que no se reconoce se devuelve limpio, sin traducir: es mejor el mensaje
    original que uno inventado.
    """
    text = _ANSI.sub("", error_text or "").strip()
    lowered = text.lower()
    for fragment, message in _FRIENDLY:
        if fragment in lowered:
            return message
    if "playlist" in lowered and "not supported" in lowered:
        return "Las playlists todavía no están soportadas."
    cleaned = _YTDLP_PREFIX.sub("", text.splitlines()[0] if text else "").strip()
    return cleaned or "Error desconocido."