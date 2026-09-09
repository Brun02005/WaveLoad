from services.set_builder_service import SetBuilderService, energy_target, interp_curve


def _tracks():
    data = [('8A', 124, 3), ('9A', 126, 5), ('8B', 125, 7),
            ('7A', 124, 9), ('8A', 128, 4), ('6A', 124, 8)]
    return [{'id': str(i), 'key': k, 'bpm': str(b), 'energy': e,
             'title': f'T{i}', 'duration': 180}
            for i, (k, b, e) in enumerate(data)]


def test_build_returns_all_steps():
    gs = SetBuilderService().build_set(_tracks(), 'club')
    assert len(gs.steps) == 6
    assert 0 <= gs.avg_quality <= 100 and 0 <= gs.curve_fit <= 100


def test_anchors_pin_start_and_end():
    ts = _tracks()
    gs = SetBuilderService().build_set(
        ts, 'club', anchors={'start': ts[3]['id'], 'end': ts[1]['id']})
    assert gs.steps[0].track['id'] == ts[3]['id']
    assert gs.steps[-1].track['id'] == ts[1]['id']


def test_energy_curves_direction():
    assert energy_target('warmup', 0.0) < energy_target('warmup', 1.0)     # rises
    assert energy_target('afterhours', 0.0) > energy_target('afterhours', 1.0)  # falls


def test_warmup_opens_lower_than_afterhours():
    ts = _tracks()
    sb = SetBuilderService()
    wu = sb.build_set(ts, 'warmup')
    af = sb.build_set(ts, 'afterhours')
    assert wu.steps[0].track['energy'] < af.steps[0].track['energy']


def test_evaluate_matches_order():
    ts = _tracks()
    gs = SetBuilderService()._evaluate(ts, 'club')
    assert [s.track['id'] for s in gs.steps] == [t['id'] for t in ts]


def test_interp_curve():
    pts = [0.2, 0.5, 0.9, 1.0, 0.7, 0.4]
    assert interp_curve(pts, 0.0) == 0.2
    assert interp_curve(pts, 1.0) == 0.4
    assert 0.4 < interp_curve(pts, 0.5) < 1.0


def test_custom_curve_shapes_set():
    """A mid-set-peak custom curve should place a peak-energy track near the
    middle, not at the end (where the 'club' preset would put it)."""
    ts = _tracks()
    curve = [0.2, 0.6, 1.0, 0.9, 0.4, 0.15]   # peak around position 2
    gs = SetBuilderService().build_set(ts, 'custom', curve_points=curve)
    energies = [s.track['energy'] for s in gs.steps]
    peak_pos = energies.index(max(energies))
    assert peak_pos <= len(energies) // 2 + 1
