"""Tests de la derivación y herencia de tags.

Las funciones puras se prueban solas; el servicio y el repositorio, sobre una
DB temporal. Todo headless.
"""

import uuid
from datetime import datetime, timezone

import pytest

from domain.tags import NS_BPM, NS_ENERGY, NS_KEY, NS_PLAYLIST, NS_SOURCE, Tag, TagSource
from infrastructure.database import DatabaseManager
from services.tagging_service import (
    BackfillReport,
    TaggingService,
    bpm_bucket,
    derived_tags,
    energy_band,
    inherited_tags,
    key_value,
)
from storage.tag_repository import SqliteTagRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Funciones puras
# =============================================================================

class TestBpmBucket:
    @pytest.mark.parametrize(
        "bpm,expected",
        [
            (120.0, "120-129"),
            (126.4, "120-129"),
            (129.99, "120-129"),
            (130.0, "130-139"),
            (100.0, "100-109"),
            (169.9, "160-169"),
        ],
    )
    def test_decade_buckets(self, bpm, expected):
        assert bpm_bucket(bpm) == expected

    def test_below_the_floor_is_one_open_bucket(self):
        assert bpm_bucket(92.0) == "under-100"
        assert bpm_bucket(99.9) == "under-100"

    def test_above_the_ceiling_is_one_open_bucket(self):
        assert bpm_bucket(170.0) == "170-plus"
        assert bpm_bucket(220.0) == "170-plus"

    def test_missing_bpm_gives_no_tag(self):
        assert bpm_bucket(None) is None

    def test_impossible_tempo_gives_no_tag(self):
        # Un análisis fallado no debe ensuciar el vocabulario.
        assert bpm_bucket(0.0) is None
        assert bpm_bucket(-1.0) is None
        assert bpm_bucket(9999.0) is None

    def test_garbage_gives_no_tag(self):
        assert bpm_bucket("no soy un número") is None

    def test_bucket_is_a_valid_tag_value(self):
        assert Tag(NS_BPM, bpm_bucket(126.0)).key == "bpm:120-129"


class TestKeyValue:
    @pytest.mark.parametrize(
        "raw,expected",
        [("8A", "8a"), ("8a", "8a"), ("12B", "12b"), ("1A", "1a"), (" 6A ", "6a")],
    )
    def test_normalizes_camelot(self, raw, expected):
        assert key_value(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "Am", "13A", "0A", "8C", "A8", "8"])
    def test_rejects_anything_that_is_not_camelot(self, raw):
        assert key_value(raw) is None

    def test_every_camelot_code_of_the_wheel_is_accepted(self):
        codes = [f"{n}{letter}" for n in range(1, 13) for letter in ("A", "B")]
        assert all(key_value(c) is not None for c in codes)
        assert len({key_value(c) for c in codes}) == 24


class TestEnergyBand:
    @pytest.mark.parametrize(
        "energy,expected",
        [
            (1, "low"), (3, "low"),
            (4, "mid"), (6, "mid"),
            (7, "high"), (8, "high"),
            (9, "peak"), (10, "peak"),
        ],
    )
    def test_bands(self, energy, expected):
        assert energy_band(energy) == expected

    def test_accepts_the_real_column_which_is_a_float(self):
        assert energy_band(7.0) == "high"
        assert energy_band(6.6) == "high"  # redondea a 7
        assert energy_band(6.4) == "mid"

    def test_missing_or_out_of_scale_gives_no_tag(self):
        assert energy_band(None) is None
        assert energy_band(0) is None
        assert energy_band(11) is None

    def test_the_four_bands_cover_the_whole_scale(self):
        assert all(energy_band(v) is not None for v in range(1, 11))


class TestDerivedTags:
    def test_full_analysis_gives_three_tags(self):
        tags = derived_tags(bpm=126.0, musical_key="8A", energy=7.0)
        assert {t.key for t in tags} == {"bpm:120-129", "key:8a", "energy:high"}

    def test_each_dimension_is_independent(self):
        # Clave inválida no debe impedir el tag de BPM.
        tags = derived_tags(bpm=126.0, musical_key="Am", energy=None)
        assert {t.key for t in tags} == {"bpm:120-129"}

    def test_nothing_analyzed_gives_nothing(self):
        assert derived_tags() == ()
        assert derived_tags(None, None, None) == ()

    def test_only_uses_derived_namespaces(self):
        tags = derived_tags(bpm=126.0, musical_key="8A", energy=7.0)
        assert {t.namespace for t in tags} == {NS_BPM, NS_KEY, NS_ENERGY}


class TestInheritedTags:
    def test_platform_and_playlist(self):
        tags = inherited_tags("youtube", "Summer Vibes 2025")
        assert {t.key for t in tags} == {"source:youtube", "playlist:summer-vibes-2025"}

    def test_platform_alone(self):
        assert {t.key for t in inherited_tags("local", None)} == {"source:local"}

    def test_blank_values_are_ignored(self):
        assert inherited_tags(None, None) == ()
        assert inherited_tags("", "   ") == ()

    def test_a_name_that_normalizes_to_nothing_is_dropped_not_raised(self):
        assert inherited_tags("youtube", "---") == (Tag(NS_SOURCE, "youtube"),)

    def test_only_uses_inherited_namespaces(self):
        tags = inherited_tags("youtube", "Mi Playlist")
        assert {t.namespace for t in tags} == {NS_SOURCE, NS_PLAYLIST}


class TestBackfillReport:
    def test_unchanged_is_what_is_left_over(self):
        report = BackfillReport(tracks_seen=10, tracks_changed=3, skipped=1)
        assert report.unchanged == 6

    def test_str_is_readable(self):
        text = str(BackfillReport(tracks_seen=5, tracks_changed=2, tags_added=6))
        assert "5 tracks vistos" in text and "+6" in text


# =============================================================================
# Servicio + repositorio sobre DB temporal
# =============================================================================

@pytest.fixture
def repo(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "tagging.db")
    return SqliteTagRepository(db=db)


@pytest.fixture
def service(repo):
    return TaggingService(repo)


def _add_track(repo, title="Track", platform=None, playlist=None,
               bpm=None, key=None, energy=None) -> str:
    track_id = str(uuid.uuid4())
    with repo.db.get_connection() as conn:
        conn.execute(
            "INSERT INTO tracks (id, title, created_at, updated_at,"
            " source_platform, source_playlist_name) VALUES (?,?,?,?,?,?)",
            (track_id, title, _now(), _now(), platform, playlist),
        )
        if bpm is not None or key is not None or energy is not None:
            conn.execute(
                "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                " analyzed_at) VALUES (?,?,?,?,?)",
                (track_id, bpm, key, energy, _now()),
            )
        conn.commit()
    return track_id


class TestRepositoryBasics:
    def test_assign_creates_the_tag_in_the_vocabulary(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "Techno"))
        assert [t.key for t in repo.all_tags()] == ["genre:techno"]
        assert [a.tag.key for a in repo.tags_for_track(track_id)] == ["genre:techno"]

    def test_assigning_twice_is_harmless(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "techno"))
        repo.assign(track_id, Tag("genre", "techno"))
        assert repo.count_assignments() == 1

    def test_the_same_tag_from_two_sources_is_two_assignments(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "techno"), TagSource.MANUAL)
        repo.assign(track_id, Tag("genre", "techno"), TagSource.AI, confidence=0.6)
        assert repo.count_assignments() == 2
        assert repo.count_assignments(TagSource.AI) == 1
        assert len(repo.all_tags()) == 1  # un solo tag en el vocabulario

    def test_unassign_can_target_one_source(self, repo):
        track_id = _add_track(repo)
        tag = Tag("genre", "techno")
        repo.assign(track_id, tag, TagSource.MANUAL)
        repo.assign(track_id, tag, TagSource.AI)
        assert repo.unassign(track_id, tag, TagSource.AI) == 1
        assert [a.source for a in repo.tags_for_track(track_id)] == [TagSource.MANUAL]

    def test_unassign_without_source_removes_all(self, repo):
        track_id = _add_track(repo)
        tag = Tag("genre", "techno")
        repo.assign(track_id, tag, TagSource.MANUAL)
        repo.assign(track_id, tag, TagSource.AI)
        assert repo.unassign(track_id, tag) == 2
        assert repo.tags_for_track(track_id) == []

    def test_unassign_a_tag_that_never_existed(self, repo):
        track_id = _add_track(repo)
        assert repo.unassign(track_id, Tag("genre", "nunca-usado")) == 0

    def test_track_ids_with_tag(self, repo):
        a = _add_track(repo, "A")
        b = _add_track(repo, "B")
        _add_track(repo, "C")
        repo.assign(a, Tag("mood", "dark"))
        repo.assign(b, Tag("mood", "dark"))
        assert set(repo.track_ids_with_tag(Tag("mood", "dark"))) == {a, b}

    def test_count_by_namespace(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "techno"))
        repo.assign(track_id, Tag("genre", "minimal"))
        repo.assign(track_id, Tag("mood", "dark"))
        assert repo.count_by_namespace() == {"genre": 2, "mood": 1}

    def test_delete_unused_tags_keeps_the_assigned_ones(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "techno"))
        with repo.db.get_connection() as conn:
            repo.get_or_create_tag_id(Tag("genre", "huerfano"), conn)
            conn.commit()
        assert len(repo.all_tags()) == 2
        assert repo.delete_unused_tags() == 1
        assert [t.key for t in repo.all_tags()] == ["genre:techno"]

    def test_tags_for_track_can_filter_by_source(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "techno"), TagSource.MANUAL)
        repo.assign(track_id, Tag("mood", "dark"), TagSource.AI)
        manual = repo.tags_for_track(track_id, TagSource.MANUAL)
        assert [a.tag.key for a in manual] == ["genre:techno"]


class TestSetTagsForSource:
    def test_replaces_only_its_own_source(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "minimal"), TagSource.MANUAL)
        repo.set_tags_for_source(track_id, TagSource.DERIVED, [Tag("bpm", "120-129")])
        keys = {(a.tag.key, a.source) for a in repo.tags_for_track(track_id)}
        assert keys == {
            ("genre:minimal", TagSource.MANUAL),
            ("bpm:120-129", TagSource.DERIVED),
        }

    def test_removes_what_is_no_longer_derived(self, repo):
        track_id = _add_track(repo)
        repo.set_tags_for_source(track_id, TagSource.DERIVED, [Tag("bpm", "120-129")])
        added, removed = repo.set_tags_for_source(
            track_id, TagSource.DERIVED, [Tag("bpm", "130-139")]
        )
        assert (added, removed) == (1, 1)
        assert [a.tag.key for a in repo.tags_for_track(track_id)] == ["bpm:130-139"]

    def test_an_empty_list_clears_the_source(self, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "techno"), TagSource.MANUAL)
        repo.set_tags_for_source(track_id, TagSource.DERIVED, [Tag("bpm", "120-129")])
        added, removed = repo.set_tags_for_source(track_id, TagSource.DERIVED, [])
        assert (added, removed) == (0, 1)
        assert [a.tag.key for a in repo.tags_for_track(track_id)] == ["genre:techno"]

    def test_unchanged_assignments_keep_their_created_at(self, repo):
        track_id = _add_track(repo)
        repo.set_tags_for_source(track_id, TagSource.DERIVED, [Tag("bpm", "120-129")])
        first = repo.tags_for_track(track_id)[0].created_at
        # Segunda corrida con el mismo tag más uno nuevo.
        repo.set_tags_for_source(
            track_id, TagSource.DERIVED, [Tag("bpm", "120-129"), Tag("key", "8a")]
        )
        by_key = {a.tag.key: a for a in repo.tags_for_track(track_id)}
        assert by_key["bpm:120-129"].created_at == first

    def test_is_idempotent(self, repo):
        track_id = _add_track(repo)
        tags = [Tag("bpm", "120-129"), Tag("key", "8a")]
        assert repo.set_tags_for_source(track_id, TagSource.DERIVED, tags) == (2, 0)
        assert repo.set_tags_for_source(track_id, TagSource.DERIVED, tags) == (0, 0)
        assert repo.count_assignments() == 2


class TestSyncPerTrack:
    def test_sync_derived_writes_the_three_tags(self, service, repo):
        track_id = _add_track(repo, bpm=126.0, key="8A", energy=7.0)
        assert service.sync_derived(track_id, 126.0, "8A", 7.0) == (3, 0)
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "bpm:120-129", "key:8a", "energy:high"
        }

    def test_reanalysis_moves_the_tags(self, service, repo):
        track_id = _add_track(repo)
        service.sync_derived(track_id, 126.0, "8A", 7.0)
        service.sync_derived(track_id, 145.0, "9A", 10.0)
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "bpm:140-149", "key:9a", "energy:peak"
        }

    def test_reanalysis_never_touches_manual_tags(self, service, repo):
        track_id = _add_track(repo)
        repo.assign(track_id, Tag("genre", "minimal"), TagSource.MANUAL)
        repo.assign(track_id, Tag("context", "peak-time"), TagSource.MANUAL)
        service.sync_derived(track_id, 126.0, "8A", 7.0)
        service.sync_derived(track_id, 90.0, None, 2.0)
        manual = {a.tag.key for a in repo.tags_for_track(track_id, TagSource.MANUAL)}
        assert manual == {"genre:minimal", "context:peak-time"}

    def test_sync_inherited(self, service, repo):
        track_id = _add_track(repo, platform="youtube", playlist="Summer Vibes")
        assert service.sync_inherited(track_id, "youtube", "Summer Vibes") == (2, 0)
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "source:youtube", "playlist:summer-vibes"
        }

    def test_derived_and_inherited_coexist(self, service, repo):
        track_id = _add_track(repo, platform="local", bpm=126.0)
        service.sync_derived(track_id, 126.0, None, None)
        service.sync_inherited(track_id, "local", None)
        assert {a.tag.key for a in repo.tags_for_track(track_id)} == {
            "bpm:120-129", "source:local"
        }


class TestBackfill:
    def test_tags_every_analyzed_track(self, service, repo):
        _add_track(repo, "A", bpm=126.0, key="8A", energy=7.0)
        _add_track(repo, "B", bpm=145.0, key="3B", energy=10.0)
        _add_track(repo, "C sin análisis")

        report = service.backfill_derived()
        assert report.tracks_seen == 2  # sólo los que tienen fila en track_analysis
        assert report.tracks_changed == 2
        assert report.tags_added == 6
        assert report.tags_removed == 0
        assert repo.count_assignments(TagSource.DERIVED) == 6

    def test_second_run_changes_nothing(self, service, repo):
        _add_track(repo, "A", bpm=126.0, key="8A", energy=7.0)
        _add_track(repo, "B", bpm=145.0, key="3B", energy=10.0)
        service.backfill_derived()

        second = service.backfill_derived()
        assert (second.tags_added, second.tags_removed) == (0, 0)
        assert second.tracks_changed == 0
        assert second.unchanged == 2
        assert repo.count_assignments(TagSource.DERIVED) == 6

    def test_partially_analyzed_tracks_get_what_they_have(self, service, repo):
        _add_track(repo, "Sólo bpm", bpm=126.0)
        report = service.backfill_derived()
        assert report.tags_added == 1

    def test_reports_progress(self, service, repo):
        for i in range(3):
            _add_track(repo, f"T{i}", bpm=126.0)
        seen = []
        service.backfill_derived(on_progress=lambda done, total: seen.append((done, total)))
        assert seen == [(1, 3), (2, 3), (3, 3)]

    def test_backfill_inherited_covers_every_track_not_just_analyzed_ones(self, service, repo):
        _add_track(repo, "A", platform="youtube", playlist="Set 1")
        _add_track(repo, "B", platform="local")
        _add_track(repo, "C")  # sin origen: no recibe tags

        report = service.backfill_inherited()
        assert report.tracks_seen == 3
        assert report.tracks_changed == 2
        assert report.tags_added == 3
        assert repo.count_by_namespace() == {"playlist": 1, "source": 2}

    def test_backfill_does_not_disturb_manual_tags(self, service, repo):
        track_id = _add_track(repo, "A", bpm=126.0)
        repo.assign(track_id, Tag("mood", "dark"), TagSource.MANUAL)
        service.backfill_derived()
        assert repo.count_assignments(TagSource.MANUAL) == 1

    def test_an_unanalyzable_row_does_not_abort_the_run(self, service, repo):
        good = _add_track(repo, "Bueno", bpm=126.0)
        bad = _add_track(repo, "Malo")
        # Una fila de análisis con basura donde va el bpm.
        with repo.db.get_connection() as conn:
            conn.execute(
                "INSERT INTO track_analysis (track_id, bpm, musical_key, energy_level,"
                " analyzed_at) VALUES (?,?,?,?,?)",
                (bad, "no soy un número", "8A", 7.0, _now()),
            )
            conn.commit()

        report = service.backfill_derived()
        assert report.tracks_seen == 2
        # El bpm corrupto simplemente no genera tag; clave y energía sí.
        assert report.errors == []
        assert {a.tag.key for a in repo.tags_for_track(good)} == {"bpm:120-129"}
        assert {a.tag.key for a in repo.tags_for_track(bad)} == {"key:8a", "energy:high"}
