"""
Unit tests for RepositoryGraph structural traversal.

The traversal is what actually feeds relationship types to the ranking
layer, so these tests pin the behaviour ranking depends on:

    - every distinct relationship type reaches the caller
    - each node is still walked only once
    - seed files do not receive structural evidence
    - distance reflects the shortest path
"""

from app.utils.repository_graph import RepositoryGraph


IMPL = "lib/data/repositories/car_repository_impl.dart"
CONTRACT = "lib/domain/repositories/car_repository.dart"
BLOC = "lib/presentation/bloc/car_bloc.dart"
STATE = "lib/presentation/bloc/car_state.dart"


def _edge(source, target, relationship):
    return {
        "source": source,
        "target": target,
        "relationship": relationship,
    }


def _key(result):
    return (
        result["target"],
        result["relationship"],
        result["distance"],
    )


def test_distinct_relationship_types_to_one_target_are_all_reported():
    """
    A repository implementation both imports and implements its
    contract. Reporting only the first edge discovered would hide
    the stronger `implements` relationship from ranking.
    """

    graph = RepositoryGraph([
        _edge(IMPL, CONTRACT, "imports"),
        _edge(IMPL, CONTRACT, "implements"),
    ])

    results = graph.get_structural_relationships([IMPL])

    assert {_key(result) for result in results} == {
        (CONTRACT, "imports", 1),
        (CONTRACT, "implements", 1),
    }


def test_extends_and_mixes_in_survive_alongside_an_import():
    graph = RepositoryGraph([
        _edge(STATE, BLOC, "imports"),
        _edge(STATE, BLOC, "extends"),
        _edge(STATE, BLOC, "mixes_in"),
    ])

    results = graph.get_structural_relationships([STATE])

    assert {
        result["relationship"]
        for result in results
    } == {"imports", "extends", "mixes_in"}


def test_the_same_relationship_type_is_reported_once_at_shortest_distance():
    """
    Ten files importing one model must not produce ten import edges
    at increasing distances for that model.
    """

    model = "lib/data/models/car.dart"

    graph = RepositoryGraph([
        _edge(IMPL, model, "imports"),
        _edge(BLOC, model, "imports"),
        _edge(IMPL, BLOC, "imports"),
    ])

    results = graph.get_structural_relationships(
        [IMPL],
        max_depth=3,
    )

    model_edges = [
        result
        for result in results
        if result["target"] == model
    ]

    assert len(model_edges) == 1
    assert model_edges[0]["distance"] == 1


def test_seed_files_do_not_receive_structural_evidence():
    """
    Seeds were found by direct retrieval. Handing them structural
    score as well would double-count them.
    """

    graph = RepositoryGraph([
        _edge(IMPL, CONTRACT, "imports"),
        _edge(CONTRACT, IMPL, "imports"),
    ])

    results = graph.get_structural_relationships(
        [IMPL, CONTRACT],
        max_depth=2,
    )

    assert results == []


def test_distance_increases_with_each_hop():
    graph = RepositoryGraph([
        _edge(BLOC, IMPL, "imports"),
        _edge(IMPL, CONTRACT, "implements"),
    ])

    results = graph.get_structural_relationships(
        [BLOC],
        max_depth=2,
    )

    by_target = {
        result["target"]: result["distance"]
        for result in results
    }

    assert by_target == {
        IMPL: 1,
        CONTRACT: 2,
    }


def test_reverse_relationships_are_followed_when_requested():
    graph = RepositoryGraph([
        _edge(BLOC, IMPL, "imports"),
    ])

    forward_only = graph.get_structural_relationships([IMPL])

    with_reverse = graph.get_structural_relationships(
        [IMPL],
        include_reverse=True,
    )

    assert forward_only == []
    assert {_key(result) for result in with_reverse} == {
        (BLOC, "imports", 1),
    }


def test_cycles_terminate():
    graph = RepositoryGraph([
        _edge("a.dart", "b.dart", "imports"),
        _edge("b.dart", "c.dart", "imports"),
        _edge("c.dart", "a.dart", "imports"),
    ])

    results = graph.get_structural_relationships(
        ["a.dart"],
        max_depth=10,
        include_reverse=True,
    )

    assert {result["target"] for result in results} == {
        "b.dart",
        "c.dart",
    }
