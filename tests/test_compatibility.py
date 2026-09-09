from services.compatibility_service import harmonic_relation, CompatibilityService


def test_same_key_perfecta():
    assert harmonic_relation('8A', '8A')[0] == 'Perfecta'


def test_relative():
    assert harmonic_relation('8A', '8B')[0] == 'Relativa'


def test_adjacent_up_down():
    assert harmonic_relation('8A', '9A')[0] == 'Subir energía'
    assert harmonic_relation('8A', '7A')[0] == 'Bajar energía'


def test_energy_boost_and_subidon():
    assert harmonic_relation('8A', '10A')[0] == 'Impulso energía'
    assert harmonic_relation('8A', '3A')[0].startswith('Subidón')


def test_incompatible_is_none():
    assert harmonic_relation('8A', '2B') is None


def test_wheel_wraps():
    assert harmonic_relation('1A', '12A')[0] == 'Bajar energía'
    assert harmonic_relation('12A', '1A')[0] == 'Subir energía'


def test_categories_are_distinct():
    cats = {harmonic_relation('8A', k)[1] for k in ('8A', '8B', '9A', '7A', '10A', '3A')}
    assert cats == {0, 1, 2, 3, 4, 5}


def test_find_compatible_excludes_self_and_dedups():
    target = {'id': 't', 'key': '8A', 'bpm': '124'}
    cands = [
        {'id': 'a', 'key': '8A', 'bpm': '125'},
        {'id': 'b', 'key': '8B', 'bpm': '126'},
        {'id': 'c', 'key': '2B', 'bpm': '124'},   # incompatible key
        {'id': 't', 'key': '8A', 'bpm': '124'},   # self
    ]
    res = CompatibilityService.find_compatible(target, cands)
    ids = [r.id for r in res]
    assert 't' not in ids and 'c' not in ids
    assert 'a' in ids and 'b' in ids


def test_find_compatible_bpm_out_of_range_excluded():
    target = {'id': 't', 'key': '8A', 'bpm': '124'}
    cands = [{'id': 'far', 'key': '8A', 'bpm': '160'}]
    assert CompatibilityService.find_compatible(target, cands) == []
