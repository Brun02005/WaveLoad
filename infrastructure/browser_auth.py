"""
infrastructure/browser_auth.py
===============================
Multi-browser cookie extraction module for WAVELOAD.

Extracts cookies for a given URL domain from the user's installed browsers,
writes them to a temporary Netscape-format cookie file compatible with
yt-dlp's ``--cookies`` flag, and returns the file path.

Browser priority order (exact):
    1. Chrome
    2. Firefox
    3. Edge
    4. Opera
    5. Brave
    6. Chromium
    7. Vivaldi
    8. Safari
    9. Opera GX
    10. LibreWolf

If extraction fails for one browser, the module automatically falls back to
the next one.  If all browsers fail, ``get_cookies_for_ytdlp`` returns
``None`` and the caller should proceed without cookies.

Dependencies
------------
- browser-cookie3  (``pip install browser-cookie3``)

Usage
-----
::

    from infrastructure.browser_auth import get_cookies_for_ytdlp, cleanup_cookie_file

    cookie_path = get_cookies_for_ytdlp("https://www.youtube.com/watch?v=xxxx")
    if cookie_path:
        # pass to yt-dlp via opts["cookiefile"] = cookie_path
        ...
        cleanup_cookie_file(cookie_path)
"""

from __future__ import annotations

import logging
import os
import tempfile
from http.cookiejar import CookieJar
from typing import Callable, Optional
from urllib.parse import urlparse

from domain.exceptions import CookieError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Browser registry
# ---------------------------------------------------------------------------

# Each entry is (display_name, browser_cookie3_loader_callable).
# The loader is resolved lazily so that import errors are caught at call time,
# not at module import time.
_BROWSER_LOADERS: list[tuple[str, str]] = [
    ("Chrome",    "chrome"),
    ("Firefox",   "firefox"),
    ("Edge",      "edge"),
    ("Opera",     "opera"),
    ("Brave",     "brave"),
    ("Chromium",  "chromium"),
    ("Vivaldi",   "vivaldi"),
    ("Safari",    "safari"),
    ("Opera GX",  "opera_gx"),
    ("LibreWolf", "librewolf"),
]

# Netscape cookie file header required by yt-dlp / curl / wget.
_NETSCAPE_HEADER = (
    "# Netscape HTTP Cookie File\n"
    "# https://curl.haxx.se/rfc/cookie_spec.html\n"
    "# This is a generated file!  Do not edit.\n\n"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_loader(browser_attr: str) -> Optional[Callable[..., CookieJar]]:
    """
    Resolve a ``browser_cookie3`` loader function by attribute name.

    Returns ``None`` if ``browser_cookie3`` is not installed or the attribute
    does not exist.
    """
    try:
        import browser_cookie3  # type: ignore[import]
        loader = getattr(browser_cookie3, browser_attr, None)
        return loader  # type: ignore[return-value]
    except ImportError:
        logger.warning(
            "browser-cookie3 is not installed. "
            "Install it with: pip install browser-cookie3"
        )
        return None


def _domain_from_url(url: str) -> str:
    """Extract the registrable domain from a URL (e.g. 'youtube.com')."""
    try:
        parsed = urlparse(url.strip())
        host = parsed.hostname or ""
        # Strip leading 'www.' for broader matching.
        return host.lstrip("www.")
    except Exception:
        return ""


def _extract_browser_cookies(
    display_name: str,
    browser_attr: str,
    domain_name: str,
) -> Optional[CookieJar]:
    """
    Attempt to load cookies from a single browser for *domain_name*.

    Parameters
    ----------
    display_name:
        Human-readable browser name used in log messages.
    browser_attr:
        Attribute name on the ``browser_cookie3`` module (e.g. ``"chrome"``).
    domain_name:
        Domain string to filter cookies (e.g. ``"youtube.com"``).

    Returns
    -------
    CookieJar | None
        Cookie jar with cookies for the domain, or ``None`` on failure.
    """
    loader = _get_loader(browser_attr)
    if loader is None:
        return None

    try:
        logger.debug("Trying browser: %s (domain: %s)", display_name, domain_name)
        jar: CookieJar = loader(domain_name=domain_name)
        count = sum(1 for _ in jar)
        if count == 0:
            logger.debug("%s: no cookies found for domain '%s'.", display_name, domain_name)
            return None
        logger.info("%s: extracted %d cookie(s) for '%s'.", display_name, count, domain_name)
        return jar
    except PermissionError as exc:
        # Browser DB is locked (browser open with exclusive lock).
        logger.warning(
            "%s: database locked — browser may be open. (%s)",
            display_name, exc,
        )
        return None
    except FileNotFoundError:
        logger.debug("%s: profile directory not found, skipping.", display_name)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: unexpected error — %s", display_name, exc)
        return None


def _write_netscape_cookie_file(jar: CookieJar) -> str:
    """
    Write *jar* to a temporary file in Netscape cookie format.

    The file is created in the OS temp directory with a ``waveload_``
    prefix.  The caller is responsible for deleting it via
    :func:`cleanup_cookie_file`.

    Returns
    -------
    str
        Absolute path to the temporary cookie file.

    Raises
    ------
    CookieError
        If the file cannot be written.
    """
    try:
        fd, path = tempfile.mkstemp(prefix="waveload_cookies_", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(_NETSCAPE_HEADER)
            for cookie in jar:
                # Netscape format columns (tab-separated):
                # domain  include_subdomains  path  secure  expires  name  value
                include_subdomains = "TRUE" if cookie.domain.startswith(".") else "FALSE"
                secure = "TRUE" if cookie.secure else "FALSE"
                expires = str(int(cookie.expires)) if cookie.expires else "0"
                fh.write(
                    "\t".join([
                        cookie.domain or "",
                        include_subdomains,
                        cookie.path or "/",
                        secure,
                        expires,
                        cookie.name or "",
                        cookie.value or "",
                    ])
                    + "\n"
                )
        logger.debug("Cookie file written: %s", path)
        return path
    except OSError as exc:
        raise CookieError(
            f"Failed to write Netscape cookie file: {exc}", cause=exc
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_cookies_for_ytdlp(url: str) -> Optional[str]:
    """
    Extract cookies for the domain of *url* from the first available browser.

    Iterates through the browser priority list and returns a path to a
    temporary Netscape-format cookie file as soon as one browser succeeds.
    If all browsers fail (or ``browser-cookie3`` is not installed), returns
    ``None``.

    Parameters
    ----------
    url:
        The URL whose domain cookies are needed
        (e.g. ``"https://www.youtube.com/watch?v=xxxx"``).

    Returns
    -------
    str | None
        Absolute path to a temporary cookie file, or ``None`` if extraction
        failed for all browsers.  Remember to call
        :func:`cleanup_cookie_file` when done.

    Examples
    --------
    ::

        path = get_cookies_for_ytdlp("https://www.youtube.com/watch?v=abc")
        if path:
            ydl_opts["cookiefile"] = path
            # ... run yt-dlp ...
            cleanup_cookie_file(path)
    """
    domain = _domain_from_url(url)
    if not domain:
        logger.warning("Could not extract domain from URL: %s", url)
        return None

    logger.info("Starting cookie extraction for domain: %s", domain)

    for display_name, browser_attr in _BROWSER_LOADERS:
        jar = _extract_browser_cookies(display_name, browser_attr, domain)
        if jar is not None:
            try:
                cookie_file_path = _write_netscape_cookie_file(jar)
                logger.info(
                    "Cookies successfully extracted from %s → %s",
                    display_name, cookie_file_path,
                )
                return cookie_file_path
            except CookieError as exc:
                logger.error(
                    "Failed to write cookies from %s: %s. Trying next browser.",
                    display_name, exc,
                )
                continue

    logger.warning(
        "Cookie extraction failed for all browsers (domain: %s). "
        "Proceeding without cookies.",
        domain,
    )
    return None


def cleanup_cookie_file(path: Optional[str]) -> None:
    """
    Safely delete the temporary cookie file at *path*.

    Silently ignores errors (e.g. file already deleted, path is ``None``).

    Parameters
    ----------
    path:
        Absolute path returned by :func:`get_cookies_for_ytdlp`, or
        ``None`` (no-op).
    """
    if not path:
        return
    try:
        os.remove(path)
        logger.debug("Cleaned up cookie file: %s", path)
    except OSError as exc:
        logger.debug("Could not remove cookie file '%s': %s", path, exc)
