"""Tests del puente entre el formulario de una capa y el AST."""

import pytest

from domain.query_ast import (
    and_,
    compare,
    not_,
    or_,
    range_,
    source,
    tag,
    tag_any,
    text,
)
from services.layer_form import (
    JOIN_AND,
    JOIN_OR,
    Condition,
    LayerForm,
    LayerFormError,
)


class TestCondition:
    def test_a_leaf_is_a_condition(self):
        assert Condition(tag("genre", "techno")).to_ast() == tag("genre", "techno")

    def test_a_negated_condition_wraps_in_not(self):
        assert Condition(tag("genre", "techno"), negated=True).to_ast() == not_(
            tag("genre", "techno")
        )

    def test_a_bool_node_is_not_a_condition(self):
        with pytest.raises(LayerFormError, match="nodo simple"):
            Condition(and_(tag("genre", "techno"), tag("mood", "dark")))

    def test_describe_reads_naturally(self):
        assert Condition(tag("genre", "techno")).describe() == "genre:techno"
        assert Condition(tag("genre", "techno"), True).describe() == "no genre:techno"


class TestToAst:
    def test_a_single_condition_is_not_wrapped(self):
        # `and(genre:techno)` evalúa igual, pero el nodo suelto es el que se lee
        # bien en la pila y el que vuelve idéntico del round-trip.
        form = LayerForm().add(tag("genre", "techno"))
        assert form.to_ast() == tag("genre", "techno")

    def test_a_single_negated_condition_is_a_not(self):
        form = LayerForm().add(tag("genre", "techno"), negated=True)
        assert form.to_ast() == not_(tag("genre", "techno"))

    def test_two_conditions_joined_by_and(self):
        form = LayerForm(JOIN_AND).add(tag("genre", "techno")).add(range_("bpm", 122, 128))
        assert form.to_ast() == and_(tag("genre", "techno"), range_("bpm", 122, 128))

    def test_two_conditions_joined_by_or(self):
        form = LayerForm(JOIN_OR).add(tag("genre", "techno")).add(tag("genre", "minimal"))
        assert form.to_ast() == or_(tag("genre", "techno"), tag("genre", "minimal"))

    def test_a_mix_of_negated_and_plain(self):
        form = LayerForm(JOIN_AND)
        form.add(tag("genre", "techno")).add(tag("context", "already-played"), negated=True)
        assert form.to_ast() == and_(
            tag("genre", "techno"), not_(tag("context", "already-played"))
        )

    def test_an_empty_form_cannot_become_a_layer(self):
        with pytest.raises(LayerFormError, match="al menos una condición"):
            LayerForm().to_ast()

    def test_an_unknown_join_is_rejected(self):
        with pytest.raises(LayerFormError, match="unión"):
            LayerForm(join="xor")

    def test_the_join_is_case_insensitive(self):
        assert LayerForm(join="OR").join == JOIN_OR


class TestFromAst:
    @pytest.mark.parametrize(
        "node",
        [
            tag("genre", "techno"),
            tag_any("mood"),
            range_("bpm", 122, 128),
            compare("duration", "gt", 300),
            text("title", "remix"),
            source("source_platform", "youtube"),
        ],
    )
    def test_every_leaf_type_becomes_a_one_condition_form(self, node):
        form = LayerForm.from_ast(node)
        assert form is not None
        assert len(form) == 1
        assert form.conditions[0].node == node
        assert not form.conditions[0].negated

    def test_a_negated_leaf_becomes_a_negated_condition(self):
        form = LayerForm.from_ast(not_(tag("genre", "techno")))
        assert form.conditions[0].negated
        assert form.conditions[0].node == tag("genre", "techno")

    def test_an_and_of_leaves(self):
        form = LayerForm.from_ast(and_(tag("genre", "techno"), range_("bpm", 122, 128)))
        assert form.join == JOIN_AND and len(form) == 2

    def test_an_or_of_leaves(self):
        form = LayerForm.from_ast(or_(tag("genre", "techno"), tag("genre", "minimal")))
        assert form.join == JOIN_OR and len(form) == 2

    def test_an_and_with_a_negated_leaf(self):
        form = LayerForm.from_ast(
            and_(tag("genre", "techno"), not_(tag("context", "already-played")))
        )
        assert [c.negated for c in form.conditions] == [False, True]


class TestWhatDoesNotFit:
    def test_nesting_is_not_representable(self):
        # Un OR adentro de un AND: el formulario plano no lo puede dibujar.
        anidado = and_(
            or_(tag("genre", "techno"), tag("genre", "minimal")),
            range_("bpm", 122, 128),
        )
        assert LayerForm.from_ast(anidado) is None
        assert not LayerForm.is_editable(anidado)

    def test_a_not_over_a_bool_is_not_representable(self):
        assert LayerForm.from_ast(
            not_(and_(tag("genre", "techno"), tag("mood", "dark")))
        ) is None

    def test_a_leaf_is_always_editable(self):
        assert LayerForm.is_editable(tag("genre", "techno"))

    def test_what_does_not_fit_is_not_an_error(self):
        # Devuelve None, no levanta: la UI la muestra de sólo lectura en vez de
        # recortarla o romperse.
        anidado = and_(or_(tag("genre", "techno"), tag("mood", "dark")), tag_any("status"))
        assert LayerForm.from_ast(anidado) is None


class TestRoundTrip:
    @pytest.mark.parametrize(
        "node",
        [
            tag("genre", "techno"),
            not_(tag("genre", "techno")),
            and_(tag("genre", "techno"), range_("bpm", 122, 128)),
            or_(tag("genre", "techno"), tag("genre", "minimal")),
            and_(tag("genre", "techno"), not_(tag("context", "already-played"))),
            compare("bpm", "is_null"),
            text("artist", "villalobos", "contains"),
        ],
    )
    def test_ast_to_form_to_ast_is_the_identity(self, node):
        form = LayerForm.from_ast(node)
        assert form is not None
        assert form.to_ast() == node

    def test_the_round_trip_of_the_stack_layers_from_the_docs(self):
        # Las tres capas del ejemplo de ARQUITECTURA 4.3, una por una.
        capas = [
            or_(tag("genre", "techno"), tag("genre", "minimal")),
            range_("bpm", 122, 128),
            tag("context", "already-played"),
        ]
        for capa in capas:
            assert LayerForm.from_ast(capa).to_ast() == capa


class TestEditing:
    def test_remove(self):
        form = LayerForm().add(tag("genre", "techno")).add(tag("mood", "dark"))
        form.remove(0)
        assert len(form) == 1
        assert form.conditions[0].node == tag("mood", "dark")

    def test_removing_out_of_range(self):
        with pytest.raises(LayerFormError, match="posición 3"):
            LayerForm().add(tag("genre", "techno")).remove(3)

    def test_add_returns_self_so_it_chains(self):
        form = LayerForm()
        assert form.add(tag("genre", "techno")) is form

    def test_describe_of_an_and(self):
        form = LayerForm(JOIN_AND).add(tag("genre", "techno")).add(range_("bpm", 122, 128))
        assert form.describe() == "genre:techno y bpm entre 122 y 128"

    def test_describe_of_an_or(self):
        form = LayerForm(JOIN_OR).add(tag("genre", "techno")).add(tag("genre", "minimal"))
        assert form.describe() == "genre:techno o genre:minimal"

    def test_describe_of_an_empty_form(self):
        assert LayerForm().describe() == "(sin condiciones)"
