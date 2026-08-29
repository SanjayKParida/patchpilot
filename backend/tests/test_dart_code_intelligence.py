"""
Tests for the Dart CodeIntelligence adapter.

Two jobs, and they are different in kind:

    PARITY — the adapter must return exactly what the underlying Dart
    analyzers already return. It exists to change the SHAPE of an
    answer, never the answer. Anything else is a silent regression in
    Dart behaviour that the existing analyzer tests would not catch,
    because they do not go through the adapter.

    CONTRACT — the adapter must honour the promises the protocol makes
    to the core, above all that an unresolvable symbol yields None
    rather than a guess.
"""

import json
from pathlib import Path

import pytest

from app.code_intelligence.dart_adapter import DartCodeIntelligence
from app.code_intelligence.protocol import CodeIntelligence, supports
from app.code_intelligence.types import Location, Reference
from app.utils.dart.dart_structure_analyzer import DartStructureAnalyzer
from app.utils.dart.dart_symbol_locator import DartSymbolLocator
from app.utils.dart.dart_usage_analyzer import DartUsageAnalyzer


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "evalutation"
    / "fixtures"
    / "car_rental_app.json"
)


@pytest.fixture(scope="module")
def files():
    return json.loads(FIXTURE.read_text())["files"]


@pytest.fixture(scope="module")
def adapter():
    return DartCodeIntelligence()


@pytest.fixture(scope="module")
def index(adapter, files):
    return adapter.build_index(files)


def _file(path, content):
    return {"path": path, "sha": path, "content": content}


# ============================================================
# PROTOCOL CONFORMANCE
# ============================================================

def test_adapter_satisfies_the_protocol(adapter):
    assert isinstance(adapter, CodeIntelligence)


def test_adapter_claims_only_dart_files(adapter):
    assert supports(adapter, "lib/main.dart")
    assert supports(adapter, "lib/MAIN.DART")
    assert not supports(adapter, "app/main.py")
    assert not supports(adapter, "README.md")


# ============================================================
# PARITY WITH THE EXISTING ANALYZERS
# ============================================================

def test_structure_matches_the_analyzer_exactly(adapter, files):
    assert adapter.analyze_structure(files) == (
        DartStructureAnalyzer().analyze_repository(files)
    )


def test_declaration_matches_the_symbol_locator(adapter, index, files):
    locator = DartSymbolLocator()
    expected = locator.build_index(files)

    for symbol in ("CarBloc", "CarsLoading", "CarRepositoryImpl"):

        direct = locator.resolve([symbol], index=expected)
        through_adapter = adapter.declaration_of(symbol, index)

        assert direct, f"fixture no longer declares {symbol}"

        assert through_adapter == Location(
            symbol=direct[0]["symbol"],
            path=direct[0]["path"],
            line=direct[0]["line"],
            kind=direct[0]["kind"],
        )


def test_references_match_the_usage_analyzer(adapter, index, files):
    usages = DartUsageAnalyzer().analyze_repository(files)

    expected = sorted(
        (u["path"], u["line"], u["kind"])
        for u in usages
        if u["identifier"] == "CarsLoading"
    )

    actual = sorted(
        (r.path, r.line, r.kind)
        for r in adapter.references_to("CarsLoading", index)
    )

    assert expected
    assert actual == expected


def test_test_file_detection_matches_the_search_service(adapter):
    assert adapter.is_test_file("test/widget_test.dart")
    assert not adapter.is_test_file(
        "lib/presentation/bloc/car_bloc.dart"
    )


# ============================================================
# CONTRACT
# ============================================================

def test_an_unknown_symbol_resolves_to_none(adapter, index):
    assert adapter.declaration_of("NoSuchSymbol", index) is None


def test_an_ambiguous_symbol_resolves_to_none(adapter):
    """
    Two files declaring one name cannot be told apart from the name
    alone. The protocol requires None, not a coin flip.
    """

    duplicated = [
        _file("lib/a.dart", "class Duplicated {}\n"),
        _file("lib/b.dart", "class Duplicated {}\n"),
    ]

    index = adapter.build_index(duplicated)

    assert adapter.declaration_of("Duplicated", index) is None


def test_declarations_in_are_ordered_by_line(adapter):
    file = _file(
        "lib/states.dart",
        "abstract class TaskState {}\n"
        "class TaskLoading extends TaskState {}\n"
        "class TaskLoaded extends TaskState {}\n",
    )

    index = adapter.build_index([file])

    found = adapter.declarations_in("lib/states.dart", index)

    assert [item.symbol for item in found] == [
        "TaskState",
        "TaskLoading",
        "TaskLoaded",
    ]
    assert [item.line for item in found] == [1, 2, 3]


def test_declarations_in_an_unknown_path_is_empty(adapter, index):
    assert adapter.declarations_in("lib/nope.dart", index) == []


def test_references_to_an_unused_symbol_is_empty(adapter, index):
    assert adapter.references_to("NoSuchSymbol", index) == []


def test_references_are_plain_records(adapter, index):
    references = adapter.references_to("CarsLoading", index)

    assert references
    assert all(isinstance(r, Reference) for r in references)


def test_non_dart_files_are_ignored_when_indexing(adapter):
    mixed = [
        _file("lib/task.dart", "class Task {}\n"),
        _file("server/task.py", "class Task:\n    pass\n"),
    ]

    index = adapter.build_index(mixed)

    declaration = adapter.declaration_of("Task", index)

    # Ambiguous only if the Python class were indexed too.
    assert declaration is not None
    assert declaration.path == "lib/task.dart"


# ============================================================
# SPANS
# ============================================================

def test_enclosing_span_resolves_against_real_source(adapter, index):
    span = adapter.enclosing_span(
        "lib/presentation/bloc/car_bloc.dart",
        6,
        index,
    )

    assert span is not None
    assert span.symbol == "CarBloc"
    assert span.start_line <= 6 <= span.end_line


def test_enclosing_span_for_an_unknown_file_is_none(adapter, index):
    assert adapter.enclosing_span("lib/nope.dart", 1, index) is None


def test_enclosing_span_is_none_when_the_locator_declines(index):
    """
    A locator that cannot answer must surface as None, not an error —
    the builder treats None as 'fall back to a fixed window'.
    """

    class Declines:
        def enclosing_span(self, path, line, content):
            return None

    adapter = DartCodeIntelligence(span_locator=Declines())

    assert adapter.enclosing_span(
        "lib/presentation/bloc/car_bloc.dart",
        6,
        index,
    ) is None
