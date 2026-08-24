"""
Unit tests for DartEvidenceAnalyzer.

The analyzer answers "how does this file mention the issue's concepts",
which is stronger information than "does the word appear". These tests
pin two things: the evidence types and strengths it reports, and the
matching rule it uses to decide a concept was mentioned at all.
"""

import pytest

from app.utils.dart.dart_evidence_analyzer import DartEvidenceAnalyzer


CAR = {"term": "car", "type": "domain"}
FIREBASE = {"term": "firebase", "type": "technology"}


@pytest.fixture
def analyzer():
    return DartEvidenceAnalyzer()


def _file(content, path="lib/example.dart"):
    return {
        "path": path,
        "sha": path,
        "content": content,
    }


def _identifiers(evidence, evidence_type=None, concept=None):
    return {
        item["identifier"]
        for item in evidence
        if (evidence_type is None
            or item["evidence_type"] == evidence_type)
        and (concept is None or item["concept"] == concept)
    }


def _types(evidence, identifier):
    return {
        item["evidence_type"]
        for item in evidence
        if item["identifier"] == identifier
    }


# ============================================================
# EVIDENCE TYPES
# ============================================================

def test_class_declaration_is_the_strongest_evidence(analyzer):
    evidence = analyzer.analyze_file(
        _file("class CarRepositoryImpl {}"),
        [CAR],
    )

    declaration = next(
        item
        for item in evidence
        if item["evidence_type"] == "class"
    )

    assert declaration["identifier"] == "CarRepositoryImpl"
    assert declaration["concept"] == "car"
    assert declaration["strength"] == 1.0
    assert declaration["line"] == 1


def test_declaration_does_not_also_become_a_weak_identifier(analyzer):
    evidence = analyzer.analyze_file(
        _file("class CarBloc {}"),
        [CAR],
    )

    assert _types(evidence, "CarBloc") == {"class"}


def test_property_access_is_reported(analyzer):
    evidence = analyzer.analyze_file(
        _file("var snapshot = await firebase.collection('x').get();"),
        [FIREBASE],
    )

    assert "firebase" in {
        item["identifier"].lower()
        for item in evidence
    }


def test_comments_produce_no_evidence(analyzer):
    evidence = analyzer.analyze_file(
        _file(
            "// class CarRepository handles cars\n"
            "/* CarBloc lives elsewhere */\n"
            "final x = 1;\n"
        ),
        [CAR],
    )

    assert evidence == []


def test_inline_comments_produce_no_evidence(analyzer):
    evidence = analyzer.analyze_file(
        _file("final x = 1; // CarRepository"),
        [CAR],
    )

    assert evidence == []


def test_no_signals_means_no_evidence(analyzer):
    evidence = analyzer.analyze_file(
        _file("class CarRepositoryImpl {}"),
        [],
    )

    assert evidence == []


# ============================================================
# MATCHING RULE
# ============================================================

def test_plural_code_vocabulary_matches_a_singular_signal(analyzer):
    """
    Dart code says getCars / fetchCars / LoadCars while the issue says
    "car". Strict token matching without singularization would lose the
    entire call chain.
    """

    evidence = analyzer.analyze_file(
        _file(
            "class GetCars {\n"
            "  Future<List<Car>> fetchCars() {\n"
            "    return repository.getCars();\n"
            "  }\n"
            "}\n"
        ),
        [CAR],
    )

    found = _identifiers(evidence, concept="car")

    assert "GetCars" in found
    assert "fetchCars" in found
    assert "getCars" in found


def test_substring_lookalikes_do_not_produce_evidence(analyzer):
    """
    The payment-card UI must not become evidence for the car domain.
    Substring matching cannot make this distinction.
    """

    evidence = analyzer.analyze_file(
        _file(
            "class CardDetailsPage {}\n"
            "class MoreCard {}\n"
        ),
        [CAR],
    )

    assert evidence == []


def test_a_compound_containing_the_concept_still_matches(analyzer):
    """
    CarCard is a card that shows a car. It legitimately mentions the
    concept, so it must match; keeping it out of the top results is
    ranking's job, not the matcher's.
    """

    evidence = analyzer.analyze_file(
        _file("class CarCard {}"),
        [CAR],
    )

    assert _identifiers(evidence, concept="car") == {"CarCard"}


def test_concept_label_is_the_original_signal_term(analyzer):
    """
    RepositoryRankingService filters evidence by comparing `concept`
    to the signal term, so the label must survive normalization
    unchanged even when the term is plural.
    """

    evidence = analyzer.analyze_file(
        _file("class Car {}"),
        [{"term": "Cars", "type": "domain"}],
    )

    assert {item["concept"] for item in evidence} == {"cars"}


def test_duplicate_signal_terms_do_not_duplicate_evidence(analyzer):
    evidence = analyzer.analyze_file(
        _file("class CarRepository {}"),
        [CAR, {"term": "car", "type": "architecture"}],
    )

    assert len(
        [
            item
            for item in evidence
            if item["evidence_type"] == "class"
        ]
    ) == 1


def test_blank_signal_terms_are_ignored(analyzer):
    evidence = analyzer.analyze_file(
        _file("class CarRepository {}"),
        [{"term": "   ", "type": "domain"}],
    )

    assert evidence == []


# ============================================================
# CONSUMPTION EVIDENCE
# ============================================================

def test_a_resolved_reference_is_upgraded_to_consumption(analyzer):
    """
    A screen that branches on CarsLoading does not declare it, so
    ownership scoring alone treats it as a bystander. Resolving the
    reference is what tells the difference between a real repository
    type and any other token.
    """

    evidence = analyzer.analyze_file(
        _file("if (state is CarsLoading) { return Spinner(); }"),
        [{"term": "loading", "type": "behavior"}],
        consumed_symbols={
            "CarsLoading": "lib/bloc/car_state.dart",
        },
    )

    record = next(
        item
        for item in evidence
        if item["identifier"] == "CarsLoading"
    )

    assert record["evidence_type"] == "consumes"
    assert record["strength"] == (
        DartEvidenceAnalyzer.EVIDENCE_STRENGTHS["consumes"]
    )
    assert record["declared_in"] == "lib/bloc/car_state.dart"


def test_consumption_replaces_the_identifier_record(analyzer):
    """
    One occurrence is one observation. Emitting both a `consumes` and
    an `identifier` record for the same token would count it twice.
    """

    evidence = analyzer.analyze_file(
        _file("if (state is CarsLoading) {}"),
        [{"term": "loading", "type": "behavior"}],
        consumed_symbols={
            "CarsLoading": "lib/bloc/car_state.dart",
        },
    )

    assert _types(evidence, "CarsLoading") == {"consumes"}


def test_an_unresolved_reference_never_becomes_consumption(analyzer):
    """
    `CarsLoading` here names nothing this repository declares — the
    same shape as a Material icon or a third-party type. Without
    resolution it must stay a bare identifier.
    """

    evidence = analyzer.analyze_file(
        _file("if (state is CarsLoading) {}"),
        [CAR],
        consumed_symbols={},
    )

    assert _types(evidence, "CarsLoading") == {"identifier"}


def test_consumption_is_weaker_than_declaring_the_same_concept(
    analyzer,
):
    strengths = DartEvidenceAnalyzer.EVIDENCE_STRENGTHS

    assert strengths["identifier"] < strengths["consumes"]
    assert strengths["consumes"] < strengths["class"]


def test_analyze_repository_resolves_consumption_across_files():
    """
    End to end: the owner declares, the consumer reacts, and only the
    consumer receives consumption evidence.
    """

    owner = {
        "path": "lib/bloc/car_state.dart",
        "sha": "owner",
        "content": (
            "abstract class CarState {}\n"
            "class CarsLoading extends CarState {}\n"
        ),
    }

    consumer = {
        "path": "lib/pages/car_list_screen.dart",
        "sha": "consumer",
        "content": (
            "import '../bloc/car_state.dart';\n"
            "Widget build() {\n"
            "  if (state is CarsLoading) { return Spinner(); }\n"
            "}\n"
        ),
    }

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, consumer],
        [{"term": "loading", "type": "behavior"}],
    )

    consuming = {
        item["file"]["path"]
        for item in evidence
        if item["evidence_type"] == "consumes"
    }

    declaring = {
        item["file"]["path"]
        for item in evidence
        if item["evidence_type"] == "class"
    }

    assert consuming == {consumer["path"]}
    assert declaring == {owner["path"]}


def test_only_configured_usage_kinds_become_evidence():
    """
    Construction is not consumption. Broadening the accepted kinds
    was measured and rejected — see CONTEXT.md — so the default must
    stay narrow.
    """

    assert DartEvidenceAnalyzer.CONSUMPTION_KINDS == ("state_test",)

    owner = {
        "path": "lib/bloc/car_bloc.dart",
        "sha": "owner",
        "content": "class CarBloc {}\n",
    }

    wiring = {
        "path": "lib/injection_container.dart",
        "sha": "wiring",
        "content": (
            "import 'bloc/car_bloc.dart';\n"
            "void init() { register(CarBloc()); }\n"
        ),
    }

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, wiring],
        [{"term": "bloc", "type": "architecture"}],
    )

    assert not [
        item
        for item in evidence
        if item["evidence_type"] == "consumes"
    ]


# ============================================================
# BEHAVIORAL-FLOW EVIDENCE
# ============================================================

LOADING = {"term": "loading", "type": "behavior"}


def _lifecycle_files():
    owner = {
        "path": "lib/bloc/car_state.dart",
        "sha": "owner",
        "content": (
            "abstract class CarState {}\n"
            "class CarsLoading extends CarState {}\n"
            "class CarsLoaded extends CarState {}\n"
            "class CarsError extends CarState {}\n"
        ),
    }
    screen = {
        "path": "lib/pages/car_list_screen.dart",
        "sha": "screen",
        "content": (
            "import '../bloc/car_state.dart';\n"
            "Widget build() {\n"
            "  if (state is CarsLoading) { return Spinner(); }\n"
            "  if (state is CarsLoaded) { return ListView(); }\n"
            "  if (state is CarsError) { return Error(); }\n"
            "}\n"
        ),
    }
    return owner, screen


def test_reacting_to_a_behavior_lifecycle_emits_behavior_flow():
    """
    The screen branches on CarsLoading AND its siblings. That is the
    UI for the loading lifecycle, not merely consumption of a type
    whose name contains "loading".
    """

    owner, screen = _lifecycle_files()

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, screen],
        [LOADING],
    )

    flow = next(
        item
        for item in evidence
        if item["evidence_type"] == "behavior_flow"
    )

    assert flow["file"]["path"] == screen["path"]
    assert flow["concept"] == "loading"
    assert flow["identifier"] == "CarState"
    assert flow["members"] == [
        "CarsError",
        "CarsLoaded",
        "CarsLoading",
    ]
    assert flow["strength"] == (
        DartEvidenceAnalyzer.EVIDENCE_STRENGTHS["behavior_flow"]
    )


def test_behavior_flow_does_not_replace_consumption():
    """
    They are different observations. Consuming CarsLoading still
    counts; reacting to the family is extra, not instead.
    """

    owner, screen = _lifecycle_files()

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, screen],
        [LOADING],
    )

    screen_types = {
        item["evidence_type"]
        for item in evidence
        if item["file"]["path"] == screen["path"]
        and item["concept"] == "loading"
    }

    assert "consumes" in screen_types
    assert "behavior_flow" in screen_types


def test_testing_only_the_matching_type_is_not_a_flow():
    """
    `state is CarsLoading` alone is generic type consumption.
    A lifecycle has more than one member under test.
    """

    owner, _ = _lifecycle_files()
    screen = {
        "path": "lib/pages/car_list_screen.dart",
        "sha": "screen",
        "content": (
            "import '../bloc/car_state.dart';\n"
            "Widget build() {\n"
            "  if (state is CarsLoading) { return Spinner(); }\n"
            "}\n"
        ),
    }

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, screen],
        [LOADING],
    )

    assert not [
        item
        for item in evidence
        if item["evidence_type"] == "behavior_flow"
    ]


def test_siblings_that_do_not_match_the_behavior_are_not_a_flow():
    """
    CarsLoaded / CarsError belong to the family, but neither name
    matches "loading". A widget that only handles the success and
    error branches is not the loading UI.
    """

    owner, _ = _lifecycle_files()
    screen = {
        "path": "lib/pages/car_list_screen.dart",
        "sha": "screen",
        "content": (
            "import '../bloc/car_state.dart';\n"
            "Widget build() {\n"
            "  if (state is CarsLoaded) { return ListView(); }\n"
            "  if (state is CarsError) { return Error(); }\n"
            "}\n"
        ),
    }

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, screen],
        [LOADING],
    )

    assert not [
        item
        for item in evidence
        if item["evidence_type"] == "behavior_flow"
    ]


def test_constructing_the_lifecycle_is_not_a_flow():
    """
    The BLoC emits every state. That is ownership of the machine,
    already scored by declarations, not a reaction to it.
    """

    owner, _ = _lifecycle_files()
    bloc = {
        "path": "lib/bloc/car_bloc.dart",
        "sha": "bloc",
        "content": (
            "import 'car_state.dart';\n"
            "class CarBloc {\n"
            "  CarBloc() : super(CarsLoading());\n"
            "  void load() {\n"
            "    emit(CarsLoading());\n"
            "    emit(CarsLoaded([]));\n"
            "    emit(CarsError('x'));\n"
            "  }\n"
            "}\n"
        ),
    }

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, bloc],
        [LOADING],
    )

    assert not [
        item
        for item in evidence
        if item["evidence_type"] == "behavior_flow"
    ]


def test_behavior_flow_is_not_emitted_for_a_domain_signal():
    """
    The mechanism is about the symptom, not the entity. CarsLoaded
    already matches "car" as consumption; the family must not
    manufacture extra domain relevance.
    """

    owner, screen = _lifecycle_files()

    evidence = DartEvidenceAnalyzer().analyze_repository(
        [owner, screen],
        [CAR],
    )

    assert not [
        item
        for item in evidence
        if item["evidence_type"] == "behavior_flow"
    ]


def test_behavior_flow_sits_between_consumes_and_a_declaration():
    strengths = DartEvidenceAnalyzer.EVIDENCE_STRENGTHS

    assert strengths["consumes"] < strengths["behavior_flow"]
    assert strengths["behavior_flow"] < strengths["function"]
    assert strengths["behavior_flow"] < strengths["class"]
