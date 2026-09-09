from services.graph_service import GraphService


def _tracks():
    data = [('8A', 124, 5), ('9A', 125, 6), ('7A', 126, 5),
            ('8B', 124, 7), ('8A', 127, 5), ('2B', 140, 3)]
    return [{'id': str(i), 'key': k, 'bpm': str(b), 'energy': e, 'title': f'T{i}'}
            for i, (k, b, e) in enumerate(data)]


def test_build_keeps_all_analyzable_nodes():
    G = GraphService().build(_tracks())
    assert G.number_of_nodes() == 6
    assert G.number_of_edges() >= 1


def test_build_drops_unanalyzable():
    tracks = _tracks() + [{'id': 'x', 'key': '—', 'bpm': '—', 'energy': None, 'title': 'x'}]
    G = GraphService().build(tracks)
    assert 'x' not in G.nodes()


def test_communities_cover_all_nodes():
    gs = GraphService()
    G = gs.build(_tracks())
    comm = gs.communities(G)
    assert set(comm.keys()) == set(G.nodes())


def test_shortest_path_endpoints():
    gs = GraphService()
    G = gs.build(_tracks())
    nodes = list(G.nodes())
    p = gs.shortest_path(G, nodes[0], nodes[1])
    assert p is None or (p[0] == nodes[0] and p[-1] == nodes[1])
