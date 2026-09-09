"""Tests del AST de predicados (domain/query_ast.py). Puro, sin DB."""

import json

import pytest

from domain.query_ast import (
    AST_VERSION,
    BoolNode,
    CompareNode,
    QueryASTError,
    RangeNode,
    SourceNode,
    TagAnyNode,
    TagNode,
    TextNode,
    and_,
    compare,
    not_,
    or_,
    parse,
    parse_many,
    range_,
    source,
    tag,
    tag_any,
    text,
)


@pytest.fixture
def stack():
    """El ejemplo de la sección 4.3 de ARQUITECTURA.md, como un solo predicado."""
    return and_(
        or_(tag("genre", "techno"), tag("genre", "minimal")),
        range_("bpm", 122, 128),
        not_(tag("context", "already-played")),
    )


class TestTagNode:
    def test_normalizes_namespace_and_value(self):
        node = tag("Genre", "Deep House")
        assert node.to_dict() == {"op": "tag", "namespace": "genre", "value": "deep-house"}

    def test_rejects_unknown_namespace(self):
        with pytest.raises(QueryASTError, match="Namespace desconocido"):
            tag("vibe", "dark")

    def test_rejects_a_value_that_normalizes_to_nothing(self):
        with pytest.raises(QueryASTError):
            tag("genre", "---")

    def test_describe(self):
        assert tag("genre", "techno").describe() == "genre:techno"


class TestTagAnyNode:
    def test_roundtrip(self):
        assert tag_any("mood").to_dict() == {"op": "tag_any", "namespace": "mood"}

    def test_rejects_unknown_namespace(self):
        with pytest.raises(QueryASTError):
            tag_any("vibe")


class TestRangeNode:
    def test_both_bounds(self):
        assert range_("bpm", 122, 128).to_dict() == {
            "op": "range", "field": "bpm", "min": 122, "max": 128
        }

    def test_open_bounds_are_omitted_from_the_json(self):
        assert range_("bpm", minimum=140).to_dict() == {"op": "range", "field": "bpm", "min": 140}
        assert range_("energy", maximum=3).to_dict() == {"op": "range", "field": "energy", "max": 3}

    def test_needs_at_least_one_bound(self):
        with pytest.raises(QueryASTError, match="al menos un extremo"):
            range_("bpm")

    def test_rejects_an_inverted_range(self):
        with pytest.raises(QueryASTError, match="Rango invertido"):
            range_("bpm", 140, 120)

    def test_a_single_point_range_is_valid(self):
        assert range_("bpm", 128, 128).min == 128

    def test_works_on_date_fields(self):
        node = range_("created_at", "2026-01-01", "2026-12-31")
        assert node.field == "created_at"

    def test_rejects_incomparable_bounds(self):
        with pytest.raises(QueryASTError, match="incomparables"):
            range_("bpm", 120, "muchos")

    @pytest.mark.parametrize("field", ["title", "artist", "source_platform", "genre"])
    def test_rejects_fields_that_are_not_ordered(self, field):
        with pytest.raises(QueryASTError, match="no consultable"):
            range_(field, 1, 2)


class TestCompareNode:
    def test_binary_comparator(self):
        assert compare("duration", "gt", 300).to_dict() == {
            "op": "compare", "field": "duration", "cmp": "gt", "value": 300
        }

    def test_unary_comparator_omits_the_value(self):
        assert compare("bpm", "is_null").to_dict() == {
            "op": "compare", "field": "bpm", "cmp": "is_null"
        }

    def test_unary_comparator_rejects_a_value(self):
        with pytest.raises(QueryASTError, match="no lleva valor"):
            compare("bpm", "is_null", 120)

    def test_binary_comparator_needs_a_value(self):
        with pytest.raises(QueryASTError, match="necesita un valor"):
            compare("bpm", "gt")

    def test_rejects_unknown_comparator(self):
        with pytest.raises(QueryASTError, match="Comparador desconocido"):
            compare("bpm", "aproximadamente", 120)

    def test_is_case_insensitive_on_the_comparator(self):
        assert compare("bpm", "GT", 120).cmp == "gt"

    def test_describe_reads_like_an_expression(self):
        assert compare("duration", "gt", 300).describe() == "duration > 300"
        assert compare("bpm", "is_null").describe() == "bpm sin dato"


class TestTextNode:
    def test_defaults_to_contains(self):
        assert text("title", "remix").to_dict() == {
            "op": "text", "field": "title", "value": "remix", "mode": "contains"
        }

    def test_keeps_the_value_verbatim(self):
        # A diferencia de un tag, el texto de búsqueda no se slugifica.
        assert text("artist", "Ricardo Villalobos").value == "Ricardo Villalobos"

    def test_rejects_unknown_mode(self):
        with pytest.raises(QueryASTError, match="Modo de texto desconocido"):
            text("title", "x", "regex")

    def test_rejects_an_empty_search(self):
        with pytest.raises(QueryASTError, match="necesita algo que buscar"):
            text("title", "   ")

    @pytest.mark.parametrize("field", ["bpm", "created_at", "source_platform"])
    def test_only_works_on_text_fields(self, field):
        with pytest.raises(QueryASTError, match="no consultable"):
            text(field, "x")


class TestSourceNode:
    def test_roundtrip(self):
        assert source("source_platform", "youtube").to_dict() == {
            "op": "source", "field": "source_platform", "value": "youtube"
        }

    def test_trims_but_does_not_slugify(self):
        assert source("source_playlist_name", "  Summer Vibes  ").value == "Summer Vibes"

    def test_rejects_other_fields(self):
        with pytest.raises(QueryASTError, match="no consultable"):
            source("title", "x")

    def test_rejects_an_empty_value(self):
        with pytest.raises(QueryASTError):
            source("source_platform", "")


class TestBoolNode:
    def test_and_or_serialize_their_children(self):
        node = and_(tag("genre", "techno"), tag("mood", "dark"))
        assert node.to_dict()["op"] == "and"
        assert len(node.to_dict()["children"]) == 2

    def test_not_takes_exactly_one_child(self):
        with pytest.raises(QueryASTError, match="exactamente un hijo"):
            BoolNode("not", (tag("genre", "techno"), tag("mood", "dark")))

    def test_rejects_an_empty_bool_node(self):
        with pytest.raises(QueryASTError, match="al menos un hijo"):
            and_()

    def test_rejects_a_non_node_child(self):
        with pytest.raises(QueryASTError, match="Hijo inválido"):
            BoolNode("and", ("genre:techno",))

    def test_rejects_unknown_bool_operator(self):
        with pytest.raises(QueryASTError, match="Operador booleano desconocido"):
            BoolNode("xor", (tag("genre", "techno"),))

    def test_a_single_child_and_is_allowed(self):
        # El builder visual arranca una capa con una condición sola.
        assert len(and_(tag("genre", "techno")).nodes) == 1

    def test_nesting_has_no_arbitrary_limit(self):
        node = tag("genre", "techno")
        for _ in range(20):
            node = not_(node)
        assert len(list(node.walk())) == 21


class TestWalk:
    def test_visits_every_node_in_preorder(self, stack):
        ops = [n.op for n in stack.walk()]
        assert ops == ["and", "or", "tag", "tag", "range", "not", "tag"]

    def test_a_leaf_walks_to_itself(self):
        leaf = tag("genre", "techno")
        assert list(leaf.walk()) == [leaf]

    def test_children_of_a_leaf_is_empty(self):
        assert tag("genre", "techno").children() == ()


class TestParse:
    def test_roundtrip_through_json(self, stack):
        assert parse(json.loads(json.dumps(stack.to_dict()))) == stack

    def test_roundtrip_is_stable_for_every_node_type(self):
        nodes = [
            tag("genre", "techno"),
            tag_any("mood"),
            range_("bpm", 122, 128),
            range_("energy", minimum=7),
            compare("duration", "gt", 300),
            compare("bpm", "is_null"),
            text("title", "remix", "starts_with"),
            source("source_platform", "youtube"),
            and_(tag("genre", "techno"), not_(tag_any("status"))),
        ]
        for node in nodes:
            assert parse(node.to_dict()) == node, node.describe()

    def test_parse_many(self):
        nodes = parse_many([tag("genre", "techno").to_dict(), tag_any("mood").to_dict()])
        assert [n.op for n in nodes] == ["tag", "tag_any"]

    def test_text_mode_defaults_when_absent(self):
        assert parse({"op": "text", "field": "title", "value": "x"}).mode == "contains"

    def test_rejects_a_non_object(self):
        with pytest.raises(QueryASTError, match="objeto JSON"):
            parse(["op", "tag"])

    def test_rejects_a_node_without_op(self):
        with pytest.raises(QueryASTError, match="sin 'op'"):
            parse({"namespace": "genre", "value": "techno"})

    def test_rejects_unknown_operator(self):
        with pytest.raises(QueryASTError, match="Operador desconocido"):
            parse({"op": "similar_to", "track_id": "x"})

    def test_rejects_in_collection_which_is_out_of_v1(self):
        # Documentado como fuera de alcance: tiene que fallar fuerte, no ignorarse.
        with pytest.raises(QueryASTError, match="Operador desconocido"):
            parse({"op": "in_collection", "id": 3})

    def test_rejects_unexpected_keys(self):
        # Casi siempre es un typo o un AST de otra versión.
        with pytest.raises(QueryASTError, match="Llaves inesperadas"):
            parse({"op": "tag", "namespace": "genre", "value": "techno", "confidence": 0.5})

    def test_reports_the_missing_key_by_name(self):
        with pytest.raises(QueryASTError, match="'namespace'"):
            parse({"op": "tag", "value": "techno"})

    def test_rejects_children_that_are_not_a_list(self):
        with pytest.raises(QueryASTError, match="tiene que ser una lista"):
            parse({"op": "and", "children": {"op": "tag_any", "namespace": "mood"}})

    def test_an_error_deep_in_the_tree_surfaces(self):
        broken = {
            "op": "and",
            "children": [
                {"op": "tag", "namespace": "genre", "value": "techno"},
                {"op": "range", "field": "bpm", "min": 200, "max": 100},
            ],
        }
        with pytest.raises(QueryASTError, match="Rango invertido"):
            parse(broken)

    def test_operator_is_case_insensitive(self):
        assert parse({"op": "TAG", "namespace": "genre", "value": "techno"}).op == "tag"


class TestDescribe:
    def test_full_stack_reads_as_an_expression(self, stack):
        assert stack.describe() == (
            "((genre:techno OR genre:minimal) AND bpm entre 122 y 128 "
            "AND NOT (context:already-played))"
        )

    def test_str_is_describe(self):
        node = tag("genre", "techno")
        assert str(node) == node.describe()


class TestVersion:
    def test_the_current_ast_version_is_one(self):
        # Si esto cambia, hay que migrar los ast_json ya guardados.
        assert AST_VERSION == 1
