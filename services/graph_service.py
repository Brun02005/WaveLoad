"""
services/graph_service.py
=========================
Builds the Music Knowledge Graph from the analysed library: nodes are tracks,
edges are strong harmonic+tempo transitions (scored by SimilarityEngine). Uses
NetworkX for the graph, a force-directed layout, community detection and
shortest-path routing (Path Finder). Pure/Qt-free.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from services.similarity_service import SimilarityEngine
from services.compatibility_service import _parse_camelot, _parse_bpm

logger = logging.getLogger(__name__)


class GraphService:
    def __init__(self, threshold: int = 70, edges_per_node: int = 6):
        self.engine = SimilarityEngine()
        self.threshold = threshold
        self.edges_per_node = edges_per_node  # k-NN cap so the graph stays readable

    @staticmethod
    def analyzable(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [t for t in tracks
                if _parse_camelot(t.get("key")) and _parse_bpm(t.get("bpm")) is not None]

    def build(self, tracks: List[Dict[str, Any]]) -> nx.Graph:
        """Build the pruned knowledge graph from presentation dicts."""
        nodes = self.analyzable(tracks)
        G = nx.Graph()
        for t in nodes:
            G.add_node(t["id"], **t)

        # Collect all candidate edges (harmonically compatible + above threshold).
        candidates: Dict[str, List[Tuple[int, str, dict]]] = {t["id"]: [] for t in nodes}
        for i in range(len(nodes)):
            a = nodes[i]
            for j in range(i + 1, len(nodes)):
                b = nodes[j]
                ts = self.engine.score(a, b)
                if not ts.compatible or ts.score < self.threshold:
                    continue
                attrs = {"score": ts.score, "weight": 1.0 / max(ts.score, 1),
                         "relation": ts.relation, "bpm_delta": ts.bpm_delta}
                candidates[a["id"]].append((ts.score, b["id"], attrs))
                candidates[b["id"]].append((ts.score, a["id"], attrs))

        # Keep each node's top-K strongest edges (union → mutual keeps survive).
        for node_id, edges in candidates.items():
            edges.sort(key=lambda e: e[0], reverse=True)
            for score, other, attrs in edges[: self.edges_per_node]:
                if not G.has_edge(node_id, other):
                    G.add_edge(node_id, other, **attrs)

        logger.info(f"Knowledge graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G

    @staticmethod
    def layout(G: nx.Graph, prev_pos: Optional[Dict[str, Tuple[float, float]]] = None
               ) -> Dict[str, Tuple[float, float]]:
        """Force-directed node positions, always rescaled to roughly [-1, 1].

        `prev_pos` (positions from the last build) seeds the known nodes so the
        map stays roughly consistent as tracks are added, while newly-added
        nodes get an initial position. We deliberately do NOT pin nodes with
        `fixed`, because that skips NetworkX's rescale step and lets coordinates
        blow up over successive incremental builds.
        """
        n = G.number_of_nodes()
        if n == 0:
            return {}
        k = 2.5 / (n ** 0.5)
        init = None
        if prev_pos:
            init = {node: prev_pos[node] for node in G.nodes() if node in prev_pos}
            init = init or None
        return nx.spring_layout(G, pos=init, seed=42, k=k, iterations=30)

    @staticmethod
    def communities(G: nx.Graph) -> Dict[str, int]:
        """Assign each node a community index (graph-modularity clustering)."""
        if G.number_of_edges() == 0:
            return {n: 0 for n in G.nodes()}
        try:
            comms = nx.community.greedy_modularity_communities(G, weight="score")
        except Exception:
            return {n: 0 for n in G.nodes()}
        mapping: Dict[str, int] = {}
        for idx, community in enumerate(comms):
            for n in community:
                mapping[n] = idx
        for n in G.nodes():
            mapping.setdefault(n, 0)
        return mapping

    @staticmethod
    def shortest_path(G: nx.Graph, src: str, dst: str) -> Optional[List[str]]:
        """Best musical route between two tracks (lower total 1/score = better)."""
        if src not in G or dst not in G:
            return None
        try:
            return nx.shortest_path(G, src, dst, weight="weight")
        except nx.NetworkXNoPath:
            return None
