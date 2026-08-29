"""
Tests for DartSpanLocator.

This is the only genuinely new parsing in the ContextBuilder work, so
it carries the most risk. The tests are weighted accordingly: the
awkward cases come first, because brace matching is easy to get right
on a tidy class and wrong on everything real.

The governing rule is that an uncertain answer must be None. Several
tests assert exactly that, and they are as important as the ones
asserting a correct span — a plausible-but-wrong span silently
truncates the code a patch generator reasons about.
"""

import json
from pathlib import Path

import pytest

from app.utils.dart.dart_span_locator import DartSpanLocator


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "evalutation"
    / "fixtures"
    / "car_rental_app.json"
)


@pytest.fixture
def locator():
    return DartSpanLocator()


def span_of(locator, content, line, path="lib/example.dart"):
    return locator.enclosing_span(path, line, content)


# ============================================================
# THE CASES THAT BREAK NAIVE BRACE COUNTING
# ============================================================

def test_named_parameters_do_not_end_a_declaration(locator):
    """
    Dart writes named parameters in braces. Counting them as a body
    ends the declaration at its own parameter list — here that would
    report line 1 instead of line 3.
    """

    content = (
        "void configure({required int retries}) {\n"  # 1
        "  doThing();\n"                              # 2
        "}\n"                                         # 3
    )

    span = span_of(locator, content, 1)

    assert (span.start_line, span.end_line) == (1, 3)


def test_a_class_with_a_named_parameter_constructor_closes(locator):
    """
    The shape that appears throughout the demo repository. The class
    must still close at its own closing brace, not inside the
    constructor's parameter list.
    """

    content = (
        "class CarBloc {\n"                                  # 1
        "  CarBloc({required this.getCars}) : super(x) {\n"  # 2
        "    on<LoadCars>((event, emit) async {\n"           # 3
        "      emit(CarsLoading());\n"                       # 4
        "    });\n"                                          # 5
        "  }\n"                                              # 6
        "}\n"                                                # 7
    )

    span = span_of(locator, content, 1)

    assert (span.start_line, span.end_line) == (1, 7)


def test_a_constructor_resolves_to_its_enclosing_class(locator):
    """
    Constructors have no return type, so DartSymbolLocator does not
    treat them as declarations — and this reuses its patterns
    deliberately, so the pack keeps one definition.

    The consequence is pinned here rather than left to be discovered:
    a line inside a constructor yields the class. That is the right
    answer given no location will ever point at a constructor, but it
    is a coarser slice than a method would give.
    """

    content = (
        "class CarBloc {\n"                                  # 1
        "  CarBloc({required this.getCars}) : super(x) {\n"  # 2
        "    doThing();\n"                                   # 3
        "  }\n"                                              # 4
        "}\n"                                                # 5
    )

    span = span_of(locator, content, 3)

    assert span.symbol == "CarBloc"
    assert span.kind == "class"
    assert (span.start_line, span.end_line) == (1, 5)


def test_a_brace_inside_a_string_does_not_end_a_declaration(locator):
    content = (
        "class A {\n"
        "  final s = '}';\n"
        "  void go() {}\n"
        "}\n"
    )

    span = span_of(locator, content, 1)

    assert (span.start_line, span.end_line) == (1, 4)


def test_a_brace_inside_a_comment_does_not_end_a_declaration(locator):
    content = (
        "class A {\n"
        "  // }\n"
        "  /* } */\n"
        "  void go() {}\n"
        "}\n"
    )

    span = span_of(locator, content, 1)

    assert (span.start_line, span.end_line) == (1, 5)


def test_an_expression_body_ends_at_the_semicolon(locator):
    content = (
        "class A {\n"
        "  Future<void> load() => repository.fetch();\n"
        "  void other() {}\n"
        "}\n"
    )

    span = span_of(locator, content, 2)

    assert (span.start_line, span.end_line) == (2, 2)


def test_an_expression_body_containing_a_closure(locator):
    """
    `=> setState(() { ... })` puts a brace after the arrow, but inside
    parentheses. It is not a block body.
    """

    content = (
        "class A {\n"
        "  void go() => setState(() { value = 1; });\n"
        "}\n"
    )

    span = span_of(locator, content, 2)

    assert (span.start_line, span.end_line) == (2, 2)


def test_an_abstract_method_has_no_body(locator):
    content = (
        "abstract class CarRepository {\n"
        "  Future<List<Car>> fetchCars();\n"
        "}\n"
    )

    span = span_of(locator, content, 2)

    assert (span.start_line, span.end_line) == (2, 2)


def test_a_brace_on_a_later_line_is_still_found(locator):
    content = (
        "class CarsLoading\n"
        "    extends CarState\n"
        "    implements Marker {\n"
        "  final int n = 1;\n"
        "}\n"
    )

    span = span_of(locator, content, 1)

    assert (span.start_line, span.end_line) == (1, 5)


# ============================================================
# NESTING
# ============================================================

def test_the_innermost_declaration_wins(locator):
    """
    A line inside a method yields the method, not the class around it.
    The caller merges and pads; a tight span is the more useful
    primitive.
    """

    content = (
        "class A {\n"          # 1
        "  void first() {\n"   # 2
        "    doThing();\n"     # 3
        "  }\n"                # 4
        "  void second() {\n"  # 5
        "    other();\n"       # 6
        "  }\n"                # 7
        "}\n"                  # 8
    )

    inner = span_of(locator, content, 3)
    assert (inner.start_line, inner.end_line) == (2, 4)
    assert inner.symbol == "first"

    outer = span_of(locator, content, 1)
    assert (outer.start_line, outer.end_line) == (1, 8)
    assert outer.symbol == "A"


def test_a_line_between_members_belongs_to_the_class(locator):
    content = (
        "class A {\n"
        "  void first() {}\n"
        "\n"
        "  void second() {}\n"
        "}\n"
    )

    span = span_of(locator, content, 3)

    assert span.symbol == "A"
    assert (span.start_line, span.end_line) == (1, 5)


def test_span_carries_path_kind_and_symbol(locator):
    content = "class TaskBloc {\n  void go() {}\n}\n"

    span = span_of(locator, content, 1, path="lib/bloc/task.dart")

    assert span.path == "lib/bloc/task.dart"
    assert span.kind == "class"
    assert span.symbol == "TaskBloc"
    assert span.line_count == 3


# ============================================================
# DECLINING RATHER THAN GUESSING
# ============================================================

def test_an_unclosed_declaration_yields_none(locator):
    content = "class A {\n  void go() {\n"

    assert span_of(locator, content, 1) is None


def test_a_line_outside_any_declaration_yields_none(locator):
    content = (
        "import 'package:flutter/material.dart';\n"
        "\n"
        "class A {}\n"
    )

    assert span_of(locator, content, 1) is None


def test_a_line_past_the_end_of_the_file_yields_none(locator):
    assert span_of(locator, "class A {}\n", 99) is None


@pytest.mark.parametrize("line", [0, -1, None])
def test_a_nonsense_line_yields_none(locator, line):
    assert span_of(locator, "class A {}\n", line) is None


def test_empty_content_yields_none(locator):
    assert span_of(locator, "", 1) is None


def test_a_declaration_longer_than_the_cap_yields_none(locator):
    body = "    doThing();\n" * (DartSpanLocator.MAX_SPAN_LINES + 10)
    content = f"class Huge {{\n{body}}}\n"

    assert span_of(locator, content, 1) is None


# ============================================================
# AGAINST REAL SOURCE
# ============================================================

@pytest.fixture(scope="module")
def repository():
    files = json.loads(FIXTURE.read_text())["files"]
    return {file["path"]: file["content"] for file in files}


def test_spans_a_real_bloc_class(locator, repository):
    path = "lib/presentation/bloc/car_bloc.dart"
    content = repository[path]

    # `class CarBloc extends Bloc<CarEvent, CarState> {`
    start = next(
        number
        for number, text in enumerate(content.splitlines(), start=1)
        if text.startswith("class CarBloc")
    )

    span = locator.enclosing_span(path, start, content)

    assert span is not None
    assert span.symbol == "CarBloc"
    assert span.start_line == start
    # The class runs to the last line of the file.
    assert span.end_line == len(content.rstrip().splitlines())


def test_a_widget_constructor_call_is_not_a_declaration(locator):
    """
    `const Icon(...)` used to match the shared function pattern
    because `const` was accepted as a return type. It is not a
    declaration, so it must not be flagged — and the enclosing
    method is the span a line inside the widget tree belongs to.
    """

    content = (
        "class TaskList {\n"
        "  Widget build() {\n"
        "    return Column(children: [\n"
        "      const Icon(Icons.error_outline, size: 40),\n"
        "      const SizedBox(height: 12),\n"
        "    ]);\n"
        "  }\n"
        "}\n"
    )

    lines = locator.structure.mask_source(content).splitlines()

    flagged = {
        (kind, symbol)
        for _, kind, symbol in locator.declarations(lines)
    }

    assert flagged == {
        ("class", "TaskList"),
        ("function", "build"),
    }

    span = span_of(locator, content, 4)

    assert span.symbol == "build"
    assert (span.start_line, span.end_line) == (2, 7)


def test_calls_inside_a_body_do_not_abandon_the_declaration(locator):
    """
    Regression. The call-shape rule above must apply ONLY to a
    declaration's own signature.

    Applied inside a body too, every `Text('a'),` in a list literal
    looks like a call-shaped false positive, and real classes stop
    resolving — measured at the time as three real classes and a real
    method silently losing their spans.
    """

    content = (
        "class TaskList {\n"
        "  Widget build() {\n"
        "    return Column(children: [\n"
        "      const Text('a'),\n"
        "      const Text('b'),\n"
        "    ]);\n"
        "  }\n"
        "}\n"
    )

    span = span_of(locator, content, 1)

    assert span is not None, "a real class must still resolve"
    assert (span.start_line, span.end_line) == (1, 8)


def test_an_async_method_still_resolves(locator):
    """
    `) async {` puts a keyword between the parameter list and the
    body. The call-shape rule must not mistake it for an argument.
    """

    content = (
        "class Repo {\n"
        "  Future<List<Task>> call(TaskFilter filter) async {\n"
        "    return [];\n"
        "  }\n"
        "}\n"
    )

    span = span_of(locator, content, 2)

    assert span.symbol == "call"
    assert (span.start_line, span.end_line) == (2, 4)


def test_a_return_constructor_call_is_not_a_declaration(locator):
    """
    `return Column(children: [` used to match as a function named
    Column because `return` was accepted as a return type. The
    enclosing method is the declaration that contains that line.
    """

    content = (
        "class TaskList {\n"
        "  Widget build() {\n"
        "    return Column(children: [\n"
        "      const Text('a'),\n"
        "    ]);\n"
        "  }\n"
        "}\n"
    )

    span = span_of(locator, content, 3)

    assert span.symbol == "build"
    assert (span.start_line, span.end_line) == (2, 6)


def test_every_class_in_the_fixture_closes(locator, repository):
    """
    A sweep, not a spot check. Any Dart shape in the corpus that the
    locator cannot close is a gap in the heuristic, and this is where
    it shows up rather than in a silent truncation later.
    """

    unresolved = []

    for path, content in repository.items():

        if not path.endswith(".dart"):
            continue

        lines = locator.structure.mask_source(content).splitlines()

        for number, kind, symbol in locator.declarations(lines):

            if kind != "class":
                continue

            if locator.span_end(lines, number) is None:
                unresolved.append(f"{path}:{number} {symbol}")

    assert unresolved == []
