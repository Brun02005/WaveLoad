"""Reparto de columnas de la tabla de pistas según el espacio disponible."""

import pytest

from ui.components.tables import (
    COL_ARTIST, COL_DATE, COL_GENRE, COL_TITLE, FLEX_COLUMNS, fit_columns,
)


@pytest.mark.parametrize("ancho", [1400, 1100, 900, 700, 560, 420])
def test_the_title_is_always_readable(ancho):
    # El bug: con poco espacio el título quedaba en "…" y no se sabía qué tema era.
    anchos = fit_columns(ancho)
    assert anchos[COL_TITLE] >= FLEX_COLUMNS[COL_TITLE][1]
    assert COL_ARTIST in anchos


@pytest.mark.parametrize("ancho", [1400, 1100, 900, 700, 560, 420])
def test_the_columns_fill_the_width_without_overflow(ancho):
    assert sum(fit_columns(ancho).values()) == ancho


def test_with_room_everything_is_shown():
    assert len(fit_columns(1400)) == 9


def test_the_date_is_the_first_to_go():
    anchos = fit_columns(800)  # todo junto necesita 818
    assert COL_DATE not in anchos and COL_GENRE in anchos


def test_an_empty_genre_column_does_not_take_space():
    con, sin = fit_columns(1000, has_genres=True), fit_columns(1000, has_genres=False)
    assert COL_GENRE not in sin
    assert sin[COL_TITLE] > con[COL_TITLE]
