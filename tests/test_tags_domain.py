"""Tests del vocabulario de tags (domain/tags.py). Headless, sin Qt ni DB."""

import pytest

from domain.tags import (
    NAMESPACES,
    AI_NAMESPACES,
    DERIVED_NAMESPACES,
    INHERITED_NAMESPACES,
    MANUAL_NAMESPACES,
    Tag,
    TagAssignment,
    TagSource,
    UnknownNamespaceError,
    normalize_value,
    validate_namespace,
)


class TestNormalizeValue:
    def test_accents_are_dropped_not_the_letters(self):
        assert normalize_value("Reggaetón") == "reggaeton"
        assert normalize_value("Música Electrónica") == "musica-electronica"
        assert normalize_value("Ñandú") == "nandu"

    def test_lowercases_and_slugifies(self):
        assert normalize_value("Peak Time") == "peak-time"

    def test_collapses_punctuation(self):
        assert normalize_value("Drum & Bass") == "drum-bass"
        assert normalize_value("  Deep   House  ") == "deep-house"

    def test_strips_leading_and_trailing_separators(self):
        assert normalize_value("--techno--") == "techno"

    def test_keeps_digits(self):
        assert normalize_value("90s Rave") == "90s-rave"

    def test_rejects_values_that_normalize_to_nothing(self):
        with pytest.raises(ValueError):
            normalize_value("---")
        with pytest.raises(ValueError):
            normalize_value("   ")

    def test_is_idempotent(self):
        once = normalize_value("Peak Time")
        assert normalize_value(once) == once


class TestValidateNamespace:
    def test_accepts_every_declared_namespace(self):
        for ns in NAMESPACES:
            assert validate_namespace(ns) == ns

    def test_is_case_insensitive(self):
        assert validate_namespace("GENRE") == "genre"

    def test_rejects_unknown(self):
        with pytest.raises(UnknownNamespaceError):
            validate_namespace("vibe")


class TestTag:
    def test_normalizes_on_construction(self):
        tag = Tag(namespace="Genre", value="Drum & Bass")
        assert tag.namespace == "genre"
        assert tag.value == "drum-bass"
        assert tag.key == "genre:drum-bass"

    def test_parse_roundtrip(self):
        assert Tag.parse("context:peak-time").key == "context:peak-time"

    def test_parse_normalizes(self):
        assert Tag.parse("genre: Deep House").key == "genre:deep-house"

    def test_parse_requires_namespace(self):
        with pytest.raises(ValueError):
            Tag.parse("techno")

    def test_rejects_unknown_namespace(self):
        with pytest.raises(UnknownNamespaceError):
            Tag(namespace="vibe", value="dark")

    def test_equality_is_by_namespace_and_value_not_id(self):
        # frozen dataclass: dos tags con el mismo par son intercambiables como
        # clave de dict aunque uno venga de la DB con id y el otro no.
        assert Tag("genre", "techno") == Tag("Genre", "TECHNO")
        assert len({Tag("genre", "techno"), Tag("genre", "Techno")}) == 1

    def test_str_is_the_canonical_key(self):
        assert str(Tag("mood", "dark")) == "mood:dark"


class TestTagSource:
    def test_serializes_as_its_string_value(self):
        assert TagSource.DERIVED.value == "derived"
        assert f"{TagSource.MANUAL.value}" == "manual"

    def test_only_manual_is_not_automatic(self):
        automatic = [s for s in TagSource if s.is_automatic]
        assert set(automatic) == {TagSource.DERIVED, TagSource.INHERITED, TagSource.AI}
        assert not TagSource.MANUAL.is_automatic


class TestNamespacePartition:
    def test_every_namespace_has_at_least_one_producer(self):
        covered = (
            MANUAL_NAMESPACES | DERIVED_NAMESPACES | INHERITED_NAMESPACES | AI_NAMESPACES
        )
        assert covered == set(NAMESPACES)

    def test_automatic_namespaces_do_not_overlap_each_other(self):
        assert not (DERIVED_NAMESPACES & INHERITED_NAMESPACES)
        assert not (DERIVED_NAMESPACES & AI_NAMESPACES)
        assert not (INHERITED_NAMESPACES & AI_NAMESPACES)

    def test_derived_and_inherited_are_never_hand_editable(self):
        # La UI de tagging manual sólo ofrece MANUAL_NAMESPACES; lo derivado y
        # lo heredado se recalcula, no se escribe a mano.
        assert not (MANUAL_NAMESPACES & DERIVED_NAMESPACES)
        assert not (MANUAL_NAMESPACES & INHERITED_NAMESPACES)


class TestTagAssignment:
    def test_defaults_to_manual_with_full_confidence(self):
        a = TagAssignment(track_id="t1", tag=Tag("genre", "techno"))
        assert a.source is TagSource.MANUAL
        assert a.confidence == 1.0

    def test_same_tag_can_come_from_two_sources(self):
        tag = Tag("genre", "techno")
        manual = TagAssignment("t1", tag, TagSource.MANUAL)
        ai = TagAssignment("t1", tag, TagSource.AI, confidence=0.7)
        assert manual.tag == ai.tag
        assert manual.source is not ai.source
