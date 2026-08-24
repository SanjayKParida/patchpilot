"""
Unit tests for RepositoryRankingService.

These tests pin the ranking contract with small in-memory fixtures so
that scoring behaviour can be verified without the live GitHub harness.

They encode four rules:

    1. Direct code evidence reaches the score at all.
    2. Evidence strength matters more than evidence quantity.
    3. The three direct channels observe ONE fact and must not be
       summed as if they were three independent facts.
    4. Every structural relationship the analyzer emits is scored,
       and structural evidence stays subordinate to direct evidence.
"""

import pytest

from app.services.repository_ranking_service import (
    RepositoryRankingService,
)


TECHNOLOGY_SIGNAL = {"term": "firebase", "type": "technology"}


def _file(path, sha=None):
    return {"path": path, "sha": sha or path, "content": ""}


def _evidence(
    file,
    evidence_type,
    strength,
    concept="firebase",
    count=1,
):
    """Build `count` evidence records of one type for one file."""

    return [
        {
            "file": file,
            "evidence_type": evidence_type,
            "concept": concept,
            "strength": strength,
            "line": line,
            "identifier": "FirebaseCarDataSource",
        }
        for line in range(1, count + 1)
    ]


def _content(file, match_type="code", count=1):
    return [
        {
            "file": file,
            "line": line,
            "text": "...",
            "match_type": match_type,
        }
        for line in range(1, count + 1)
    ]


def _structural(file, relationship, distance=1):
    return {
        "file": file,
        "source": "lib/seed.dart",
        "target": file["path"],
        "relationship": relationship,
        "distance": distance,
    }


def _rank(
    service,
    signal=TECHNOLOGY_SIGNAL,
    path_results=None,
    content_results=None,
    structural_results=None,
    direct_evidence=None,
):
    return service.rank(
        signal=signal,
        path_results=path_results or [],
        content_results=content_results or [],
        structural_results=structural_results,
        direct_evidence=direct_evidence,
    )


@pytest.fixture
def service():
    return RepositoryRankingService()


# ============================================================
# CHANNEL COMBINATION
# ============================================================

def test_channels_are_not_summed(service):
    """
    The core Phase 2 rule. Path, content and evidence are three
    observations of one fact — that the file is about the concept —
    so a file matching all three must score far below the sum of
    three files each matching one.
    """

    everything = _file("lib/firebase_options.dart")

    combined = _rank(
        service,
        path_results=[everything],
        content_results=_content(everything, count=4),
        direct_evidence=_evidence(everything, "class", 1.0),
    )[everything["sha"]]["direct_score"]

    separate = 0.0

    for kwargs in (
        {"path_results": [_file("lib/a.dart")]},
        {"content_results": _content(_file("lib/b.dart"), count=4)},
        {"direct_evidence": _evidence(_file("lib/c.dart"), "class", 1.0)},
    ):
        scores = _rank(service, **kwargs)
        separate += next(iter(scores.values()))["direct_score"]

    assert combined < separate


def test_direct_score_is_bounded_by_the_signal_weight(service):
    """
    However loudly one file shouts a single concept, its direct score
    for that signal cannot exceed the signal's weight. This is what
    stops intensity on one concept from beating breadth across many.
    """

    shouty = _file("lib/firebase_options.dart")

    score = _rank(
        service,
        path_results=[shouty],
        content_results=_content(shouty, count=500),
        direct_evidence=(
            _evidence(shouty, "class", 1.0, count=50)
            + _evidence(shouty, "function", 0.9, count=50)
            + _evidence(shouty, "identifier", 0.2, count=500)
        ),
    )[shouty["sha"]]["direct_score"]

    weight = RepositoryRankingService.SIGNAL_WEIGHTS["technology"]

    assert score <= weight


def test_corroboration_still_helps(service):
    """
    Not summing is not the same as ignoring. A second channel claims
    a share of what the first left uncertain, so agreement still
    raises the score.
    """

    one = _file("lib/a.dart")
    two = _file("lib/b.dart")

    scores = _rank(
        service,
        path_results=[one, two],
        content_results=_content(two, count=2),
    )

    assert (
        scores[two["sha"]]["direct_score"]
        > scores[one["sha"]]["direct_score"]
    )


def test_evidence_is_the_most_trusted_channel(service):
    """
    A file the language pack saw declaring the concept must outrank a
    file that merely has the word in its name or on a line.
    """

    declaring = _file("lib/a.dart")
    named = _file("lib/firebase_thing.dart")
    mentioning = _file("lib/c.dart")

    scores = _rank(
        service,
        path_results=[named],
        content_results=_content(mentioning, count=3),
        direct_evidence=(
            _evidence(declaring, "class", 1.0)
            + _evidence(declaring, "function", 0.9)
        ),
    )

    direct = scores[declaring["sha"]]["direct_score"]

    assert direct > scores[named["sha"]]["direct_score"]
    assert direct > scores[mentioning["sha"]]["direct_score"]


def test_content_is_the_weakest_channel(service):
    """
    Content is the fallback for what evidence cannot see. On its own
    it must be worth less than the file being named for the concept.
    """

    named = _file("lib/firebase_options.dart")
    mentioning = _file("lib/other.dart")

    scores = _rank(
        service,
        path_results=[named],
        content_results=_content(mentioning, count=3),
    )

    assert (
        scores[named["sha"]]["direct_score"]
        > scores[mentioning["sha"]]["direct_score"]
    )


def test_breadth_across_signals_beats_intensity_on_one(service):
    """
    The failure this whole design exists to prevent: a generated
    config file that mentions one concept everywhere outranking a
    file that matches several of the issue's concepts.
    """

    config = _file("lib/firebase_options.dart")
    relevant = _file("lib/data/car_repository_impl.dart")

    intense = _rank(
        service,
        signal=TECHNOLOGY_SIGNAL,
        path_results=[config],
        content_results=_content(config, count=20),
        direct_evidence=_evidence(config, "class", 1.0, count=5),
    )

    broad = [
        _rank(
            service,
            signal=signal,
            direct_evidence=_evidence(
                relevant,
                "class",
                1.0,
                concept=signal["term"],
            ),
        )
        for signal in (
            {"term": "car", "type": "domain"},
            {"term": "repository", "type": "architecture"},
            {"term": "loading", "type": "behavior"},
        )
    ]

    final = service.aggregate([intense] + broad)

    assert (
        final[relevant["sha"]]["total_score"]
        > final[config["sha"]]["total_score"]
    )


# ============================================================
# EVIDENCE QUALITY
# ============================================================

def test_stronger_evidence_types_outrank_weaker_ones(service):
    declaring = _file("lib/a.dart")
    mentioning = _file("lib/b.dart")

    scores = _rank(
        service,
        direct_evidence=(
            _evidence(declaring, "class", 1.0)
            + _evidence(mentioning, "identifier", 0.2)
        ),
    )

    assert (
        scores[declaring["sha"]]["direct_score"]
        > scores[mentioning["sha"]]["direct_score"]
    )


def test_many_weak_mentions_cannot_outrank_one_declaration(service):
    """
    Guards against a widget that repeats an identifier dozens of
    times outranking the class that declares it.
    """

    declaring = _file("lib/a.dart")
    chatty = _file("lib/b.dart")

    scores = _rank(
        service,
        direct_evidence=(
            _evidence(declaring, "class", 1.0)
            + _evidence(chatty, "identifier", 0.2, count=50)
        ),
    )

    assert (
        scores[declaring["sha"]]["direct_score"]
        > scores[chatty["sha"]]["direct_score"]
    )


def test_distinct_evidence_types_stack(service):
    declares_only = _file("lib/a.dart")
    declares_and_uses = _file("lib/b.dart")

    scores = _rank(
        service,
        direct_evidence=(
            _evidence(declares_only, "class", 1.0)
            + _evidence(declares_and_uses, "class", 1.0)
            + _evidence(declares_and_uses, "property_access", 0.7)
        ),
    )

    assert (
        scores[declares_and_uses["sha"]]["direct_score"]
        > scores[declares_only["sha"]]["direct_score"]
    )


def test_evidence_for_another_concept_is_ignored(service):
    """
    rank() scores one signal at a time, so the caller may hand it the
    whole evidence set without pre-filtering.
    """

    file = _file("lib/a.dart")

    scores = _rank(
        service,
        direct_evidence=_evidence(file, "class", 1.0, concept="bloc"),
    )

    assert scores == {}


def _score_by_signal_type(service, signal_type):
    file = _file("lib/a.dart")

    scores = _rank(
        service,
        signal={"term": "firebase", "type": signal_type},
        direct_evidence=_evidence(file, "class", 1.0),
    )

    return scores[file["sha"]]["direct_score"]


def test_signal_weight_scales_the_direct_score(service):
    weights = RepositoryRankingService.SIGNAL_WEIGHTS

    ratio = (
        weights["technology"]
        / weights["domain"]
    )

    assert _score_by_signal_type(service, "technology") == (
        pytest.approx(
            _score_by_signal_type(service, "domain") * ratio
        )
    )


def test_symptom_signals_outrank_stack_and_entity_signals(service):
    """
    A bug report's symptom word points at the broken behaviour. Its
    technology and domain words mostly describe the whole project,
    so they must not dominate.

    This ordering is what keeps a generated `firebase_options.dart`,
    which matches one loud technology signal, below files that match
    what the issue actually reports.
    """

    behavior = _score_by_signal_type(service, "behavior")
    architecture = _score_by_signal_type(service, "architecture")
    technology = _score_by_signal_type(service, "technology")
    domain = _score_by_signal_type(service, "domain")

    assert behavior > architecture > technology > domain


# ============================================================
# DEPTH VERSUS BREADTH
# ============================================================

def test_weak_mentions_of_many_concepts_lose_to_real_ownership(
    service,
):
    """
    A dependency-injection container references every concept the
    application wires together and owns none of them. It must not
    outrank the file that implements the reported behaviour purely by
    touching more concepts.
    """

    wiring = _file("lib/injection_container.dart")
    owner = _file("lib/presentation/bloc/car_bloc.dart")

    signals = [
        {"term": "firebase", "type": "technology"},
        {"term": "firestore", "type": "technology"},
        {"term": "repository", "type": "architecture"},
        {"term": "bloc", "type": "architecture"},
        {"term": "loading", "type": "behavior"},
    ]

    rankings = []

    for signal in signals:

        # The wiring file mentions every concept, weakly.
        evidence = _evidence(
            wiring,
            "identifier",
            0.2,
            concept=signal["term"],
        )

        # The owner declares two of them.
        if signal["term"] in ("bloc", "loading"):
            evidence += _evidence(
                owner,
                "class",
                1.0,
                concept=signal["term"],
            ) + _evidence(
                owner,
                "function",
                0.9,
                concept=signal["term"],
            )

        rankings.append(
            _rank(
                service,
                signal=signal,
                content_results=_content(wiring, count=3),
                direct_evidence=evidence,
            )
        )

    final = service.aggregate(rankings)

    assert final[wiring["sha"]]["signals_matched"] == 5
    assert final[owner["sha"]]["signals_matched"] == 2

    assert (
        final[owner["sha"]]["total_score"]
        > final[wiring["sha"]]["total_score"]
    )


def test_confidence_exponent_penalises_partial_confidence(service):
    """
    The exponent must bite hardest on middling confidence. A near
    certain observation should be almost untouched, while a "probably
    just mentions it" observation is heavily discounted.
    """

    exponent = RepositoryRankingService.CONFIDENCE_EXPONENT

    assert exponent >= 1.0

    strong_loss = 1.0 - (0.95 ** exponent) / 0.95
    weak_loss = 1.0 - (0.30 ** exponent) / 0.30

    assert weak_loss > strong_loss


def test_a_file_with_no_observation_is_not_scored(service):
    assert _rank(service) == {}


# ============================================================
# STRUCTURAL RELATIONSHIPS
# ============================================================

@pytest.mark.parametrize(
    "relationship",
    ["imports", "implements", "extends", "mixes_in"],
)
def test_every_analyzer_relationship_type_is_scored(
    service,
    relationship,
):
    """
    DartStructureAnalyzer emits imports / implements / extends /
    mixes_in. A relationship missing from STRUCTURAL_WEIGHTS is
    silently worth nothing, so all four must score above zero.
    """

    file = _file("lib/domain/car_repository.dart")

    scores = _rank(
        service,
        structural_results=[_structural(file, relationship)],
    )

    assert scores[file["sha"]]["structural_score"] > 0


def test_structural_relationship_weight_ordering(service):
    def score_for(relationship):
        file = _file(f"lib/{relationship}.dart")

        scores = _rank(
            service,
            structural_results=[_structural(file, relationship)],
        )

        return scores[file["sha"]]["structural_score"]

    assert score_for("extends") == score_for("implements")
    assert (
        score_for("implements")
        > score_for("mixes_in")
        > score_for("imports")
    )


def test_unknown_relationship_types_are_ignored(service):
    file = _file("lib/a.dart")

    scores = _rank(
        service,
        structural_results=[_structural(file, "smells_like")],
    )

    assert scores == {}


def test_distance_decays_structural_score(service):
    near = _file("lib/near.dart")
    far = _file("lib/far.dart")

    scores = _rank(
        service,
        structural_results=[
            _structural(near, "extends", distance=1),
            _structural(far, "extends", distance=3),
        ],
    )

    assert (
        scores[near["sha"]]["structural_score"]
        > scores[far["sha"]]["structural_score"]
    )


def test_only_the_closest_edge_of_each_relationship_type_counts(
    service,
):
    """
    A shared model imported by ten files must not accumulate ten
    import contributions.
    """

    model = _file("lib/data/models/car.dart")

    repeated = _rank(
        service,
        structural_results=[
            _structural(model, "imports", distance=1),
            _structural(model, "imports", distance=1),
            _structural(model, "imports", distance=2),
        ],
    )

    single = _rank(
        service,
        structural_results=[_structural(model, "imports")],
    )

    assert (
        repeated[model["sha"]]["structural_score"]
        == single[model["sha"]]["structural_score"]
    )


def test_direct_evidence_outweighs_structural_evidence(service):
    declaring = _file("lib/a.dart")
    neighbour = _file("lib/b.dart")

    scores = _rank(
        service,
        direct_evidence=_evidence(declaring, "class", 1.0),
        structural_results=[_structural(neighbour, "extends")],
    )

    assert (
        scores[declaring["sha"]]["direct_score"]
        > scores[neighbour["sha"]]["structural_score"]
    )


def test_structural_score_is_capped_by_direct_evidence(service):
    """
    Connectivity supports relevance; it must not manufacture it.
    """

    final = service.aggregate([
        {
            "sha-1": {
                "path": "lib/a.dart",
                "direct_score": 2.0,
                "structural_score": 10.0,
                "signals_matched": 1,
                "path_confidence": 0,
                "content_confidence": 0,
                "evidence_confidence": 1.0,
            }
        }
    ])

    ratio = RepositoryRankingService.STRUCTURAL_CAP_RATIO

    assert final["sha-1"]["structural_score"] == pytest.approx(
        2.0 * ratio
    )
    assert final["sha-1"]["total_score"] == pytest.approx(
        2.0 + 2.0 * ratio
    )


# ============================================================
# AGGREGATION
# ============================================================

def test_aggregate_sums_direct_scores_across_signals(service):
    """
    Summing across SIGNALS is deliberate — it is what rewards a file
    for matching more of the issue. Only summing across CHANNELS is
    forbidden.
    """

    file = _file("lib/a.dart")

    firebase = _rank(
        service,
        signal={"term": "firebase", "type": "technology"},
        direct_evidence=_evidence(file, "class", 1.0),
    )

    car = _rank(
        service,
        signal={"term": "car", "type": "domain"},
        direct_evidence=_evidence(file, "class", 1.0, concept="car"),
    )

    final = service.aggregate([firebase, car])[file["sha"]]

    assert final["direct_score"] == pytest.approx(
        firebase[file["sha"]]["direct_score"]
        + car[file["sha"]]["direct_score"]
    )
    assert final["signals_matched"] == 2
    assert final["total_score"] == pytest.approx(
        final["direct_score"] + final["structural_score"]
    )


def test_aggregate_counts_matched_signals(service):
    broad = _file("lib/injection_container.dart")
    narrow = _file("lib/firebase_options.dart")

    rankings = [
        _rank(
            service,
            signal={"term": term, "type": "technology"},
            direct_evidence=_evidence(
                broad,
                "identifier",
                0.2,
                concept=term,
            ),
        )
        for term in ("firebase", "firestore", "bloc")
    ]

    rankings.append(
        _rank(
            service,
            direct_evidence=_evidence(narrow, "class", 1.0),
        )
    )

    final = service.aggregate(rankings)

    assert final[broad["sha"]]["signals_matched"] == 3
    assert final[narrow["sha"]]["signals_matched"] == 1
