"""
Unit tests for DartUsageAnalyzer.

The analyzer answers "which files use a type that another file
declares". Two properties matter and are pinned here:

    Precision — a reference is only reported when it genuinely
    resolves to a repository declaration through a real import.
    A false consumption edge is worse than a missing one.

    Classification — HOW a type is used is reported separately from
    THAT it is used. Treating every reference alike makes the file
    that wires an application together look like its most relevant
    file, which is measured and documented in CONTEXT.md.
"""

import pytest

from app.utils.dart.dart_usage_analyzer import DartUsageAnalyzer


@pytest.fixture
def analyzer():
    return DartUsageAnalyzer()


def _file(path, content):
    return {"path": path, "sha": path, "content": content}


STATE = _file(
    "lib/bloc/car_state.dart",
    "abstract class CarState {}\n"
    "class CarsLoading extends CarState {}\n"
    "class CarsLoaded extends CarState {}\n",
)

BLOC = _file(
    "lib/bloc/car_bloc.dart",
    "import 'car_state.dart';\n"
    "class CarBloc {}\n",
)


def _usages(analyzer, files, path=None):
    return [
        usage
        for usage in analyzer.analyze_repository(files)
        if path is None or usage["path"] == path
    ]


def _by_identifier(usages):
    return {usage["identifier"]: usage for usage in usages}


# ============================================================
# CLASSIFICATION
# ============================================================

def test_state_test_is_detected(analyzer):
    """
    `state is CarsLoading` is the file REACTING to a state it does
    not own. This is the relationship a screen has with the bloc that
    drives it, and the one Phase 4 exists to surface.
    """

    screen = _file(
        "lib/pages/car_list_screen.dart",
        "import '../bloc/car_state.dart';\n"
        "Widget build() {\n"
        "  if (state is CarsLoading) { return Spinner(); }\n"
        "}\n",
    )

    usages = _by_identifier(
        _usages(analyzer, [STATE, screen], screen["path"])
    )

    assert usages["CarsLoading"]["kind"] == "state_test"
    assert usages["CarsLoading"]["declared_in"] == STATE["path"]
    assert usages["CarsLoading"]["line"] == 3


def test_negated_state_test_is_detected(analyzer):
    screen = _file(
        "lib/pages/screen.dart",
        "import '../bloc/car_state.dart';\n"
        "final done = state is! CarsLoading;\n",
    )

    usages = _by_identifier(
        _usages(analyzer, [STATE, screen], screen["path"])
    )

    assert usages["CarsLoading"]["kind"] == "state_test"


def test_type_arguments_are_classified_separately(analyzer):
    screen = _file(
        "lib/pages/screen.dart",
        "import '../bloc/car_state.dart';\n"
        "import '../bloc/car_bloc.dart';\n"
        "final w = BlocBuilder<CarBloc, CarState>();\n",
    )

    usages = _by_identifier(
        _usages(analyzer, [STATE, BLOC, screen], screen["path"])
    )

    assert usages["CarBloc"]["kind"] == "type_argument"
    assert usages["CarState"]["kind"] == "type_argument"


def test_construction_is_only_a_plain_reference(analyzer):
    """
    Building a thing is assembly, not use. This is what separates a
    dependency-injection container from a screen.
    """

    wiring = _file(
        "lib/service_locator.dart",
        "import 'bloc/car_bloc.dart';\n"
        "void init() { register(CarBloc()); }\n",
    )

    usages = _by_identifier(
        _usages(analyzer, [STATE, BLOC, wiring], wiring["path"])
    )

    assert usages["CarBloc"]["kind"] == "reference"


# ============================================================
# PRECISION
# ============================================================

def test_a_reference_without_an_import_is_not_consumption(analyzer):
    """
    Same rule DartStructureAnalyzer applies to implements / extends:
    a matching name elsewhere in the repository is not evidence that
    Dart resolves this reference to that declaration.
    """

    screen = _file(
        "lib/pages/screen.dart",
        "if (state is CarsLoading) {}\n",
    )

    assert _usages(analyzer, [STATE, screen], screen["path"]) == []


def test_a_file_does_not_consume_its_own_declarations(analyzer):
    assert _usages(analyzer, [STATE], STATE["path"]) == []


def test_ambiguous_symbols_are_skipped(analyzer):
    """
    Two imported files declaring the same name means the reference
    cannot be attributed without real resolution. Stay conservative.
    """

    other = _file(
        "lib/bloc/other_state.dart",
        "class CarsLoading {}\n",
    )

    screen = _file(
        "lib/pages/screen.dart",
        "import '../bloc/car_state.dart';\n"
        "import '../bloc/other_state.dart';\n"
        "if (state is CarsLoading) {}\n",
    )

    usages = _usages(
        analyzer,
        [STATE, other, screen],
        screen["path"],
    )

    assert "CarsLoading" not in _by_identifier(usages)


def test_external_package_types_are_not_consumption(analyzer):
    screen = _file(
        "lib/pages/screen.dart",
        "import 'package:flutter_bloc/flutter_bloc.dart';\n"
        "final w = BlocBuilder<Foo, Bar>();\n",
    )

    assert _usages(analyzer, [screen], screen["path"]) == []


def test_comments_and_strings_are_not_consumption(analyzer):
    screen = _file(
        "lib/pages/screen.dart",
        "import '../bloc/car_state.dart';\n"
        "// if (state is CarsLoading) {}\n"
        "final label = 'CarsLoading';\n",
    )

    assert _usages(analyzer, [STATE, screen], screen["path"]) == []


# ============================================================
# INDEX
# ============================================================

def test_consumption_index_filters_by_kind(analyzer):
    screen = _file(
        "lib/pages/screen.dart",
        "import '../bloc/car_state.dart';\n"
        "import '../bloc/car_bloc.dart';\n"
        "final w = BlocBuilder<CarBloc, CarState>();\n"
        "if (state is CarsLoading) {}\n",
    )

    files = [STATE, BLOC, screen]

    everything = analyzer.consumption_index(files)
    reactions = analyzer.consumption_index(
        files,
        kinds=("state_test",),
    )

    assert set(everything[screen["path"]]) >= {
        "CarBloc",
        "CarState",
        "CarsLoading",
    }
    assert set(reactions[screen["path"]]) == {"CarsLoading"}


# ============================================================
# TYPE FAMILIES
# ============================================================

def test_siblings_that_share_a_local_base_are_one_family(analyzer):
    """
    CarsLoading / CarsLoaded / CarsError are the lifecycle of
    CarState because they extend it in the same file, not because
    their names look similar.
    """

    families = analyzer.type_families([STATE])

    assert families[STATE["path"]]["CarState"] == {
        "CarsLoading",
        "CarsLoaded",
    }


def test_a_lone_subclass_is_not_a_family(analyzer):
    lone = _file(
        "lib/bloc/car_state.dart",
        "abstract class CarState {}\n"
        "class CarsLoading extends CarState {}\n",
    )

    assert analyzer.type_families([lone]) == {}


def test_an_external_base_does_not_form_a_family(analyzer):
    """
    Extending Equatable or a package type is not a local lifecycle.
    """

    states = _file(
        "lib/bloc/car_state.dart",
        "class CarsLoading extends Equatable {}\n"
        "class CarsLoaded extends Equatable {}\n",
    )

    assert analyzer.type_families([states]) == {}


def test_cross_file_hierarchies_are_not_families(analyzer):
    """
    Same-file only. Resolving a base declared elsewhere is a
    separate hypothesis and would need import resolution.
    """

    base = _file(
        "lib/bloc/car_state.dart",
        "abstract class CarState {}\n",
    )
    loading = _file(
        "lib/bloc/cars_loading.dart",
        "import 'car_state.dart';\n"
        "class CarsLoading extends CarState {}\n",
    )
    loaded = _file(
        "lib/bloc/cars_loaded.dart",
        "import 'car_state.dart';\n"
        "class CarsLoaded extends CarState {}\n",
    )

    assert analyzer.type_families([base, loading, loaded]) == {}


def test_comments_do_not_create_families(analyzer):
    commented = _file(
        "lib/bloc/car_state.dart",
        "abstract class CarState {}\n"
        "// class CarsLoading extends CarState {}\n"
        "class CarsLoaded extends CarState {}\n",
    )

    assert analyzer.type_families([commented]) == {}
