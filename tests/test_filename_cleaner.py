import pytest

from services.filename_cleaner_service import (
    CleanedName, clean_name, looks_mangled, plan_cleanup,
)


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Alaia_Gallo_-_Lipstick_KLICKAUD",
    "Praise_You_KLICKAUD",
    "Some Track KLICKAUD",
    "A_Place_You_Wanna_Go_Good_Life",
])
def test_looks_mangled_detects_ripper_names(title):
    assert looks_mangled(title) is True


@pytest.mark.parametrize("title", [
    "Astral Projection",
    "Avenger (Devils Cave Mix)",
    "Awake - Julian Jeweil Remix",
    "",
])
def test_looks_mangled_leaves_clean_titles_alone(title):
    assert looks_mangled(title) is False


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def test_artist_title_split():
    r = clean_name("Alaia_Gallo_-_Lipstick_KLICKAUD")
    assert r.artist == "Alaia Gallo"
    assert r.title == "Lipstick"
    assert r.confidence == "high"


def test_leading_year_is_extracted():
    r = clean_name("1994_-_Tyree_Cooper_-_Acid_Over_Remix_by_Paul_Oakenfold_KLICKAUD")
    assert r.year == "1994"
    assert r.artist == "Tyree Cooper"
    assert r.title == "Acid Over Remix by Paul Oakenfold"


def test_no_separator_cleans_title_only():
    r = clean_name("Once_Again_Back_KLICKAUD")
    assert r.artist is None
    assert r.title == "Once Again Back"
    assert r.confidence == "medium"


def test_glued_mp3_extension_removed():
    r = clean_name("Jean_Massey_Asereje_Extended_Mixmp3_KLICKAUD")
    assert r.title.endswith("Extended Mix")
    assert "mp3" not in r.title


def test_accents_are_preserved():
    r = clean_name("Nu_Genea_-_Sciallà_Junerule_Edit_KLICKAUD")
    assert r.artist == "Nu Genea"
    assert r.title == "Sciallà Junerule Edit"


def test_only_first_separator_splits_artist():
    r = clean_name("Paul_Johnson_-_Get_Get_Down_-_REMASTERED_2013_KLICKAUD")
    assert r.artist == "Paul Johnson"
    assert r.title == "Get Get Down - REMASTERED 2013"


def test_clean_title_reports_no_change():
    r = clean_name("Astral Projection")
    assert r.changed is False


def test_empty_input_is_safe():
    assert clean_name("").changed is False
    assert clean_name("   ").changed is False


def test_watermark_only_name_is_not_emptied():
    """A name that is nothing but the watermark must not become empty."""
    r = clean_name("KLICKAUD")
    assert r.title


def test_duplicate_suffix_after_watermark_is_stripped():
    """Regression: Windows appends '(1)' AFTER the watermark, so stripping
    the watermark alone left 'Foo KLICKAUD (1)' -> 'Foo KLICKAUD (1)'."""
    r = clean_name("Feels So Right Justin Winks 2008 Remix KLICKAUD (1)")
    assert "KLICKAUD" not in r.title
    assert "(1)" not in r.title
    assert r.title == "Feels So Right Justin Winks 2008 Remix"


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------

def test_plan_skips_clean_rows():
    rows = [{"id": "1", "title": "Astral Projection", "artist": "Carlos Cock"}]
    assert plan_cleanup(rows) == []


def test_plan_fills_placeholder_artist():
    rows = [{"id": "1", "title": "Alaia_Gallo_-_Lipstick_KLICKAUD", "artist": "Unknown"}]
    plan = plan_cleanup(rows)
    assert plan[0]["new_artist"] == "Alaia Gallo"
    assert plan[0]["new_title"] == "Lipstick"


def test_plan_never_overwrites_a_real_artist():
    """A user's existing artist is authoritative — only blanks get filled."""
    rows = [{"id": "1", "title": "Alaia_Gallo_-_Lipstick_KLICKAUD", "artist": "Mi Artista"}]
    plan = plan_cleanup(rows)
    assert plan[0]["new_artist"] is None
    assert plan[0]["new_title"] == "Lipstick"


def test_plan_carries_confidence():
    rows = [
        {"id": "1", "title": "Alaia_Gallo_-_Lipstick_KLICKAUD", "artist": "Unknown"},
        {"id": "2", "title": "Once_Again_Back_KLICKAUD", "artist": "Unknown"},
    ]
    plan = plan_cleanup(rows)
    assert {p["id"]: p["confidence"] for p in plan} == {"1": "high", "2": "medium"}
