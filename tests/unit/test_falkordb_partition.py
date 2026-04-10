from __future__ import annotations

from lineage_graphrag.graph.kt_builder import LineageKTBuilder
from lineage_graphrag.ingest.normalizer import LineageNormalizer
from lineage_graphrag.ingest.parser import LineageParser
from lineage_graphrag.storage.falkordb_client import _partition_graph_for_falkordb


def test_falkordb_partition_into_raw_comm_repre(fixture_payload: dict) -> None:
    parser = LineageParser()
    normalizer = LineageNormalizer()
    builder = LineageKTBuilder()

    graph = builder.build(normalizer.normalize(parser.parse(fixture_payload))).graph
    partitions = _partition_graph_for_falkordb(graph)

    raw_nodes = partitions["graph_raw"]["nodes"]
    raw_edges = partitions["graph_raw"]["edges"]
    comm_nodes = partitions["graph_comm"]["nodes"]
    comm_edges = partitions["graph_comm"]["edges"]
    repre_nodes = partitions["graph_repre"]["nodes"]
    repre_edges = partitions["graph_repre"]["edges"]

    assert raw_nodes
    assert comm_nodes
    assert repre_nodes
    assert any(graph.nodes[node_id].get("label") == "attribute" for node_id in raw_nodes)
    assert all(graph.nodes[node_id].get("label") in {"entity", "attribute"} for node_id in raw_nodes)
    assert all(str(edge_data.get("relation")) in {"has_attribute", "has", "transitions"} for _, _, edge_data in raw_edges)

    assert any(graph.nodes[node_id].get("label") == "community" for node_id in comm_nodes)
    assert any(graph.nodes[node_id].get("label") == "keyword" for node_id in comm_nodes)
    assert all(graph.nodes[node_id].get("label") in {"entity", "community", "keyword"} for node_id in comm_nodes)
    assert all(
        str(edge_data.get("relation")) in {"member_of", "has_keyword"}
        for _, _, edge_data in comm_edges
    )
    assert all(graph.nodes[node_id].get("label") in {"entity", "community", "keyword"} for node_id in repre_nodes)
    assert all(
        str(edge_data.get("relation")) in {"represents_community", "represented_by", "represents_entity"}
        for _, _, edge_data in repre_edges
    )

    assert not any(graph.nodes[node_id].get("label") == "attribute" for node_id in comm_nodes)
    assert not any(str(edge_data.get("relation")) == "has_attribute" for _, _, edge_data in comm_edges)
    assert not any(graph.nodes[node_id].get("label") == "attribute" for node_id in repre_nodes)
    assert not any(str(edge_data.get("relation")) == "has_attribute" for _, _, edge_data in repre_edges)
