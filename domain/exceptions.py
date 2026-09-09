"""
domain/exceptions.py
====================
Custom exception hierarchy for WAVELOAD.

All application-level errors derive from ``WaveloadBaseError`` so callers
can catch the entire family with a single ``except WaveloadBaseError``.
"""


class WaveloadBaseError(Exception):
    """Base class for all WAVELOAD domain exceptions."""

    def __init__(self, message: str = "", *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        base = super().__str__()
        if self.cause:
            return f"{base} (caused by: {self.cause!r})"
        return base


class UnsupportedFormatError(WaveloadBaseError):
    """
    Raised when a URL points to content that yt-dlp cannot handle,
    or when the extracted format is not compatible with the pipeline.

    Examples
    --------
    - Non-video / non-audio URL.
    - Geo-restricted content with no available format.
    - Playlist URL passed to a single-item extractor.
    """


class NetworkTemporaryError(WaveloadBaseError):
    """
    Raised for transient network failures that are worth retrying.

    This exception signals the retry decorator (tenacity) to attempt the
    operation again using exponential back-off (up to 3 attempts).

    Examples
    --------
    - HTTP 429 Too Many Requests.
    - HTTP 5xx Server Errors.
    - Socket timeout / connection reset.
    """


class CookieError(WaveloadBaseError):
    """
    Raised when cookie extraction or injection fails.

    The extractor catches this to trigger an automatic fallback retry
    without cookies.

    Examples
    --------
    - No supported browser installed / detected.
    - Browser database locked (browser still running).
    - browser-cookie3 not installed.
    - Malformed cookie file written to disk.
    """


class SpotifyResolutionError(WaveloadBaseError):
    """
    Raised when a Spotify track link cannot be turned into a playable
    YouTube match.

    Examples
    --------
    - Missing/invalid Spotify API credentials.
    - Track not found on Spotify.
    - No sufficiently confident YouTube candidate found.
    """
