"""
Slicing, merging, collapse, and budgets for ContextBuilderService.

Fixtures stay in the fake language. A `.dart` import or a brace here
means the core has grown a language assumption.
"""

from app.code_intelligence.types import (
    TIER_DEFECT,
    TIER_SUPPORTING,
    TIER_TEST,
    Span,
)
from app.services.context_budget import ContextBudget
from app.services.context_builder_service import ContextBuilderService
from app.utils.repository_graph import RepositoryGraph

from tests.test_context_builder_service import (
    FakeCodeIntelligence,
    edge,
    location,
    ranked,
)


def numbered(n):
    return "\n".join(f"L{i:03d}" for i in range(1, n + 1))


def source(path, n):
    return {"path": path, "content": numbered(n)}


def span_at(path, start, end, symbol=None):
    return Span(
        path=path,
        start_line=start,
        end_line=end,
        kind="thing",
        symbol=symbol,
    )


def package(code=None, budget=None, **kwargs):
    service = ContextBuilderService(
        code or FakeCodeIntelligence(),
        budget=budget,
    )
    kwargs.setdefault("index", object())
    return service.build(**kwargs)


def slices_for(pkg, path):
    return [item for item in pkg.slices if item.path == path]


def omitted_reason(pkg, path):
    return next(item.reason for item in pkg.omitted if item.path == path)


# Tight budgets that isolate one constraint without collapsing files.
NO_COLLAPSE = ContextBudget(
    pad_lines=0,
    whole_file_fraction=1.01,
)


# ============================================================
# SLICE SELECTION
# ============================================================

def test_resolved_declaration_uses_the_enclosing_span_plus_padding():
    path = "ui/screen.fake"
    code = FakeCodeIntelligence(
        spans={(path, 12): span_at(path, 10, 20, "Widget")},
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 12)],
        },
        files=[source(path, 50)],
        budget=ContextBudget(pad_lines=3, whole_file_fraction=1.01),
    )

    (slice,) = pkg.slices
    assert slice.start_line == 7
    assert slice.end_line == 23
    assert slice.truncated is False
    assert slice.tier == TIER_DEFECT
    assert slice.symbols == ("Widget",)
    assert slice.content.startswith("L007")
    assert slice.content.endswith("L023")


def test_missing_span_falls_back_to_a_fixed_window_and_is_marked_truncated():
    path = "ui/screen.fake"

    pkg = package(
        diagnosis={
            "root_cause_locations": [location("Widget", path, 20)],
        },
        files=[source(path, 100)],
        budget=ContextBudget(
            pad_lines=3,
            fallback_before=12,
            fallback_after=40,
            whole_file_fraction=1.01,
        ),
    )

    (slice,) = pkg.slices
    assert slice.start_line == 5
    assert slice.end_line == 63
    assert slice.truncated is True
    assert slice.content.startswith("L005")
    assert slice.content.endswith("L063")


def test_file_header_is_always_included():
    """
    Header lines are a generic preamble the fake reports, not an
    import parser. The core only unions the range the adapter names.
    """

    path = "ui/screen.fake"
    lines = ["import a", "import b"] + [f"L{i:03d}" for i in range(3, 51)]
    code = FakeCodeIntelligence(
        spans={(path, 30): span_at(path, 30, 32, "Widget")},
        headers={path: 2},
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 30)],
        },
        files=[{"path": path, "content": "\n".join(lines)}],
        budget=NO_COLLAPSE,
    )

    starts = [(item.start_line, item.end_line) for item in pkg.slices]
    assert (1, 2) in starts
    assert (30, 32) in starts
    assert pkg.slices[0].content.startswith("import a")


# ============================================================
# MERGING AND COLLAPSE
# ============================================================

def test_overlapping_slices_in_one_file_become_one():
    path = "ui/screen.fake"
    code = FakeCodeIntelligence(
        spans={
            (path, 12): span_at(path, 10, 20, "Widget"),
            (path, 19): span_at(path, 18, 25, "Helper"),
        },
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 12)],
            "locations": [location("Helper", path, 19)],
        },
        files=[source(path, 80)],
        budget=NO_COLLAPSE,
    )

    (slice,) = slices_for(pkg, path)
    assert slice.start_line == 10
    assert slice.end_line == 25
    assert slice.tier == TIER_DEFECT
    assert slice.symbols == ("Widget", "Helper")


def test_near_adjacent_slices_merge_when_the_gap_is_at_most_six():
    path = "ui/screen.fake"
    code = FakeCodeIntelligence(
        spans={
            (path, 12): span_at(path, 10, 20, "Widget"),
            (path, 28): span_at(path, 26, 30, "Helper"),
        },
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 12)],
            "locations": [location("Helper", path, 28)],
        },
        files=[source(path, 80)],
        budget=NO_COLLAPSE,
    )

    (slice,) = slices_for(pkg, path)
    assert (slice.start_line, slice.end_line) == (10, 30)


def test_slices_beyond_the_merge_gap_stay_apart():
    path = "ui/screen.fake"
    code = FakeCodeIntelligence(
        spans={
            (path, 12): span_at(path, 10, 20, "Widget"),
            (path, 29): span_at(path, 27, 30, "Helper"),
        },
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 12)],
            "locations": [location("Helper", path, 29)],
        },
        files=[source(path, 80)],
        budget=NO_COLLAPSE,
    )

    ranges = [
        (item.start_line, item.end_line) for item in slices_for(pkg, path)
    ]
    assert ranges == [(10, 20), (27, 30)]


def test_a_file_collapses_to_whole_file_past_the_retention_threshold():
    path = "ui/screen.fake"
    code = FakeCodeIntelligence(
        spans={(path, 4): span_at(path, 1, 8, "Widget")},
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 4)],
        },
        files=[source(path, 10)],
        budget=ContextBudget(
            pad_lines=0,
            whole_file_fraction=0.70,
        ),
    )

    (slice,) = pkg.slices
    assert slice.start_line == 1
    assert slice.end_line == 10
    assert slice.truncated is False
    assert pkg.files[0].complete is True


# ============================================================
# BUDGETS
# ============================================================

def test_max_files_evicts_the_lowest_tier_paths():
    pkg = package(
        diagnosis={
            "root_cause_locations": [
                location("Widget", "ui/screen.fake", 1),
            ],
        },
        ranked=ranked("lib/a.fake", "lib/b.fake", "lib/c.fake"),
        files=[
            source("ui/screen.fake", 5),
            source("lib/a.fake", 5),
            source("lib/b.fake", 5),
            source("lib/c.fake", 5),
        ],
        budget=ContextBudget(
            max_files=2,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    paths = [item.path for item in pkg.slices]
    assert paths == ["ui/screen.fake", "lib/a.fake"]
    assert pkg.budget.files_used == 2


def test_max_total_lines_evicts_from_the_back():
    pkg = package(
        diagnosis={
            "root_cause_locations": [
                location("Widget", "ui/screen.fake", 1),
            ],
        },
        ranked=ranked("lib/a.fake", "lib/b.fake"),
        files=[
            source("ui/screen.fake", 5),
            source("lib/a.fake", 5),
            source("lib/b.fake", 5),
        ],
        budget=ContextBudget(
            max_lines_total=12,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    paths = [item.path for item in pkg.slices]
    assert paths == ["ui/screen.fake", "lib/a.fake"]
    assert pkg.budget.lines_used == 10


def test_max_lines_per_file_drops_an_oversized_non_defect_file():
    pkg = package(
        diagnosis={
            "root_cause_locations": [
                location("Widget", "ui/screen.fake", 1),
            ],
        },
        ranked=ranked("lib/big.fake"),
        files=[
            source("ui/screen.fake", 5),
            source("lib/big.fake", 20),
        ],
        budget=ContextBudget(
            max_lines_per_file=10,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    assert [item.path for item in pkg.slices] == ["ui/screen.fake"]
    assert omitted_reason(pkg, "lib/big.fake") == "budget_exhausted"


def test_test_files_are_capped_separately():
    code = FakeCodeIntelligence(
        tests={"spec/a_spec.fake", "spec/b_spec.fake"},
    )
    graph = RepositoryGraph(
        [
            edge("spec/a_spec.fake", "ui/screen.fake"),
            edge("spec/b_spec.fake", "ui/screen.fake"),
        ]
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [
                location("Widget", "ui/screen.fake", 1),
            ],
        },
        ranked=ranked("spec/a_spec.fake", "spec/b_spec.fake"),
        graph=graph,
        files=[
            source("ui/screen.fake", 5),
            source("spec/a_spec.fake", 5),
            source("spec/b_spec.fake", 5),
        ],
        budget=ContextBudget(
            max_tests=1,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    test_paths = [item.path for item in pkg.slices if item.tier == TIER_TEST]
    assert test_paths == ["spec/a_spec.fake"]
    assert omitted_reason(pkg, "spec/b_spec.fake") == "budget_exhausted"


def test_eviction_is_reverse_tier():
    path = "ui/screen.fake"
    support = "core/helper.fake"
    extra = "lib/noise.fake"
    code = FakeCodeIntelligence(
        spans={
            (path, 2): span_at(path, 1, 3, "Widget"),
            (support, 2): span_at(support, 1, 3, "Helper"),
        },
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 2)],
            "locations": [location("Helper", support, 2)],
        },
        ranked=ranked(extra),
        files=[
            source(path, 10),
            source(support, 10),
            source(extra, 10),
        ],
        budget=ContextBudget(
            max_files=2,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    paths = [item.path for item in pkg.slices]
    assert extra not in paths
    assert path in paths
    assert support in paths
    assert slices_for(pkg, support)[0].tier == TIER_SUPPORTING


def test_t0_is_never_evicted_or_truncated_when_over_budget():
    path = "ui/screen.fake"
    code = FakeCodeIntelligence(
        spans={(path, 10): span_at(path, 1, 20, "Widget")},
    )

    pkg = package(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", path, 10)],
        },
        ranked=ranked("lib/noise.fake"),
        files=[source(path, 20), source("lib/noise.fake", 20)],
        budget=ContextBudget(
            max_files=1,
            max_lines_total=5,
            max_lines_per_file=5,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    (slice,) = pkg.slices
    assert slice.path == path
    assert slice.tier == TIER_DEFECT
    assert slice.start_line == 1
    assert slice.end_line == 20
    assert slice.truncated is False
    assert slice.line_count == 20
    assert pkg.budget.over_budget is True
    assert "defect site exceeds budget; included anyway" in pkg.warnings
    assert omitted_reason(pkg, "lib/noise.fake") == "budget_exhausted"


def test_building_twice_is_byte_identical():
    kwargs = dict(
        diagnosis={
            "root_cause_locations": [
                location("Widget", "ui/screen.fake", 12),
            ],
        },
        ranked=ranked("lib/a.fake", "lib/b.fake"),
        files=[
            source("ui/screen.fake", 40),
            source("lib/a.fake", 10),
            source("lib/b.fake", 10),
        ],
        issue={"number": 1, "title": "bug", "body": "it breaks"},
        budget=NO_COLLAPSE,
    )

    first = package(**kwargs)
    second = package(**kwargs)

    assert first.to_json() == second.to_json()


def test_unresolved_and_budget_omissions_are_recorded():
    pkg = package(
        diagnosis={
            "root_cause_locations": [
                location("Widget", "ui/screen.fake", 1),
            ],
        },
        ranked=ranked("lib/missing.fake", "lib/extra.fake"),
        files=[
            source("ui/screen.fake", 5),
            source("lib/extra.fake", 5),
        ],
        budget=ContextBudget(
            max_files=1,
            pad_lines=0,
            whole_file_fraction=1.01,
        ),
    )

    reasons = {item.path: item.reason for item in pkg.omitted}
    assert reasons["lib/missing.fake"] == "unresolved"
    assert reasons["lib/extra.fake"] == "budget_exhausted"
    assert pkg.files[0].path == "ui/screen.fake"
    assert pkg.language == "fake"
    assert pkg.adapter == "FakeCodeIntelligence"
    assert pkg.budget.max_files == 1
    assert pkg.slices[0].reason
    assert pkg.root_cause["symbol"] == "Widget"
