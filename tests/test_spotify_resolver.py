import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from domain.exceptions import SpotifyResolutionError
from services import spotify_resolver as sr


# --------------------------------------------------------------------------
# URL detection
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
    "https://open.spotify.com/intl-es/track/4uLU6hMCjMI75M1A2tKUQC",
    "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC?si=abc123",
    "open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
])
def test_is_spotify_track_url_accepts(url):
    assert sr.is_spotify_track_url(url) is True


@pytest.mark.parametrize("url", [
    "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
    "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "",
])
def test_is_spotify_track_url_rejects(url):
    assert sr.is_spotify_track_url(url) is False


def test_extract_track_id():
    assert sr._extract_track_id("https://open.spotify.com/track/abc123XYZ?si=1") == "abc123XYZ"


def test_extract_track_id_raises_on_non_track():
    with pytest.raises(SpotifyResolutionError):
        sr._extract_track_id("https://open.spotify.com/album/abc123")


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def test_normalize_strips_brackets_feat_and_diacritics():
    assert sr._normalize_for_match("Rosalía - Malamente (Official Video)") == "rosalia malamente"
    assert sr._normalize_for_match("Song [Lyrics] feat. Someone") == "song someone"
    assert sr._normalize_for_match("  MIXED   Case!!  ") == "mixed case"


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def test_exact_title_and_duration_scores_high():
    score = sr.score_youtube_candidate(
        "Blinding Lights", ["The Weeknd"], 200_000,
        "The Weeknd - Blinding Lights", 200,
    )
    assert score > 0.9


def test_duration_far_off_zeroes_duration_component():
    close = sr.score_youtube_candidate("Song", ["Artist"], 200_000, "Artist - Song", 200)
    far = sr.score_youtube_candidate("Song", ["Artist"], 200_000, "Artist - Song", 260)
    assert far == pytest.approx(close - sr.WEIGHT_DURATION, abs=1e-6)


def test_blacklisted_term_penalizes():
    clean = sr.score_youtube_candidate("Song", ["Artist"], 200_000, "Artist Song", 200)
    covered = sr.score_youtube_candidate("Song", ["Artist"], 200_000, "Artist Song cover", 200)
    assert covered < clean


def test_blacklisted_term_inside_brackets_still_penalizes():
    """Regression: _normalize_for_match strips bracketed text, and YouTube
    puts these markers in brackets ("(Karaoke Version)", "[8D AUDIO]"), so a
    penalty checked against the normalized title never fired."""
    clean = sr.score_youtube_candidate("Song", ["Artist"], 200_000, "Artist - Song", 200)
    bracketed = sr.score_youtube_candidate(
        "Song", ["Artist"], 200_000, "Artist - Song (Karaoke Version)", 200,
    )
    assert bracketed < clean


def test_blacklist_not_penalized_when_present_in_spotify_title():
    """A track genuinely named '... Remix' must not be punished for matching."""
    score = sr.score_youtube_candidate(
        "Song Remix", ["Artist"], 200_000, "Artist - Song Remix", 200,
    )
    assert score > 0.9


def test_missing_candidate_duration_scores_without_crashing():
    score = sr.score_youtube_candidate("Song", ["Artist"], 200_000, "Artist - Song", None)
    assert 0.0 <= score <= 1.0


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def test_find_best_match_empty_list():
    assert sr.find_best_youtube_match("Song", ["Artist"], 200_000, []) == (None, 0.0)


def test_find_best_match_all_below_threshold_returns_none():
    candidates = [{"title": "totally unrelated video", "duration": 900}]
    best, score = sr.find_best_youtube_match("Song", ["Artist"], 200_000, candidates)
    assert best is None
    assert score < sr.MIN_ACCEPT_SCORE


def test_find_best_match_picks_highest_scorer():
    candidates = [
        {"title": "Artist - Song (karaoke)", "duration": 200, "id": "bad"},
        {"title": "Artist - Song", "duration": 200, "id": "good"},
        {"title": "Something else entirely", "duration": 999, "id": "worse"},
    ]
    best, score = sr.find_best_youtube_match("Song", ["Artist"], 200_000, candidates)
    assert best["id"] == "good"
    assert score >= sr.MIN_ACCEPT_SCORE


def test_find_best_match_skips_entries_without_title():
    candidates = [None, {}, {"title": "Artist - Song", "duration": 200, "id": "good"}]
    best, _ = sr.find_best_youtube_match("Song", ["Artist"], 200_000, candidates)
    assert best["id"] == "good"


# --------------------------------------------------------------------------
# Orchestration (network mocked)
# --------------------------------------------------------------------------

_TRACK_FIXTURE = {
    "title": "Blinding Lights",
    "artists": ["The Weeknd"],
    "duration_ms": 200_000,
    "year": "2019",
    "cover_url": "https://cover.example/img.jpg",
}

# Trimmed to the fields the parser reads, in the shape the real embed page uses.
_EMBED_HTML = (
    '<html><body><script>{"entity":{"name":"Blinding Lights",'
    '"uri":"spotify:track:0VjIjW4GlUZAMYd2vXMi3b",'
    '"artists":[{"name":"The Weeknd","uri":"spotify:artist:1Xyo4u8uXC1ZmMpatF05PJ"}],'
    '"duration":200040,"releaseDate":{"isoString":"2020-03-20T00:00:00Z"},'
    '"visualIdentity":{"image":[{"url":"https://i.scdn.co/image/abc123"}]}}}'
    "</script></body></html>"
)


def test_parse_embed_html_extracts_all_fields():
    parsed = sr.parse_embed_html(_EMBED_HTML)
    assert parsed["title"] == "Blinding Lights"
    assert parsed["artists"] == ["The Weeknd"]
    assert parsed["duration_ms"] == 200040
    assert parsed["year"] == "2020"
    assert parsed["cover_url"] == "https://i.scdn.co/image/abc123"


def test_parse_embed_html_raises_on_unparseable_page():
    with pytest.raises(SpotifyResolutionError):
        sr.parse_embed_html("<html><body>nothing useful here</body></html>")


def test_parse_embed_html_unescapes_unicode():
    html = (
        '{"name":"Malamente - Cap.1: Augurio","uri":"spotify:track:x",'
        '"artists":[{"name":"Rosal\\u00eda"}],"duration":150000}'
    )
    parsed = sr.parse_embed_html(html)
    assert parsed["artists"] == ["Rosalía"]


def test_resolve_happy_path_returns_youtube_url():
    candidates = [{"title": "The Weeknd - Blinding Lights", "duration": 200, "id": "abc123"}]
    with patch.object(sr, "_fetch_track", new=AsyncMock(return_value=_TRACK_FIXTURE)), \
         patch.object(sr, "_search_youtube_candidates", new=AsyncMock(return_value=candidates)):
        result = asyncio.run(sr.resolve_spotify_url_async("https://open.spotify.com/track/xyz"))

    assert result["url"] == "https://www.youtube.com/watch?v=abc123"
    assert result["artist"] == "The Weeknd"
    assert result["duration"] == 200
    assert result["is_playlist"] is False
    assert result["source_platform"] == "spotify"
    assert result["year"] == "2019"


def test_resolve_raises_when_no_confident_match():
    candidates = [{"title": "completely different thing", "duration": 900, "id": "zzz"}]
    with patch.object(sr, "_fetch_track", new=AsyncMock(return_value=_TRACK_FIXTURE)), \
         patch.object(sr, "_search_youtube_candidates", new=AsyncMock(return_value=candidates)):
        with pytest.raises(SpotifyResolutionError):
            asyncio.run(sr.resolve_spotify_url_async("https://open.spotify.com/track/xyz"))
