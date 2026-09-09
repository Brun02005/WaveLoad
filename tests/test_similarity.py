from services.similarity_service import SimilarityEngine


def test_perfect_transition_is_excellent():
    e = SimilarityEngine()
    ts = e.score({'key': '8A', 'bpm': '124', 'energy': 5},
                 {'key': '8A', 'bpm': '124', 'energy': 5})
    assert ts.compatible and ts.score >= 90 and ts.label == 'Excelente'


def test_incompatible_key_not_compatible():
    e = SimilarityEngine()
    ts = e.score({'key': '8A', 'bpm': '124', 'energy': 5},
                 {'key': '2B', 'bpm': '124', 'energy': 5})
    assert ts.relation is None and not ts.compatible


def test_bpm_delta_reported():
    e = SimilarityEngine()
    ts = e.score({'key': '8A', 'bpm': '124', 'energy': 5},
                 {'key': '8A', 'bpm': '128', 'energy': 5})
    assert round(ts.bpm_delta) == 4


def test_score_in_range():
    e = SimilarityEngine()
    ts = e.score({'key': '8A', 'bpm': '124', 'energy': 5},
                 {'key': '9A', 'bpm': '130', 'energy': 8})
    assert 0 <= ts.score <= 100
