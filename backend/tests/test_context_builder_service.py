"""
Tests for the language-agnostic ContextBuilder core.

Every fixture here is written in a language that does not exist, and
the adapter is a fake. That is the point of the file.

If any test in it needs Dart — a `.dart` extension that matters, a
brace, an import statement with real syntax — then the core has grown
a language assumption and the abstraction has leaked. The cheapness of
adding Python and TypeScript adapters later rests entirely on this
staying true.
"""

import pytest

from app.code_intelligence.types import (
    TIER_CALLER,
    TIER_CONTRACT,
    TIER_DEFECT,
    TIER_DEPENDENCY,
    TIER_SECONDARY,
    TIER_SUPPORTING,
    TIER_TEST,
    Reference,
)
from app.services.context_builder_service import ContextBuilderService
from app.utils.repository_graph import RepositoryGraph


# ============================================================
# A FAKE LANGUAGE
# ============================================================

class FakeCodeIntelligence:
    """
    An adapter for a language that does not exist.

    It answers from data handed to the constructor rather than by
    parsing anything, which is exactly what the core is entitled to
    assume: it asks questions and does not care how they are answered.
    """

    extensions = (".fake",)
    name = "fake"

    def __init__(self, references=None, tests=(), spans=None, headers=None):
        self._references = references or {}
        self._tests = set(tests)
        self._spans = spans or {}
        self._headers = headers or {}
        self.index_calls = 0

    def build_index(self, files):
        self.index_calls += 1
        return {"files": [f["path"] for f in files]}

    def analyze_structure(self, files):
        return []

    def declaration_of(self, symbol, index):
        return None

    def declarations_in(self, path, index):
        return []

    def references_to(self, symbol, index):
        return list(self._references.get(symbol, ()))

    def enclosing_span(self, path, line, index):
        return self._spans.get((path, line))

    def header_end_line(self, path, content, index):
        return self._headers.get(path)

    def is_test_file(self, path):
        return path in self._tests


def location(symbol, path, line=1):
    return {"symbol": symbol, "path": path, "line": line, "kind": "thing"}


def ranked(*paths):
    return [
        {"path": path, "rank": number, "total_score": 10 - number}
        for number, path in enumerate(paths, start=1)
    ]


def edge(source, target, relationship="imports"):
    return {
        "source": source,
        "target": target,
        "relationship": relationship,
    }


def build(code=None, **kwargs):
    service = ContextBuilderService(code or FakeCodeIntelligence())
    kwargs.setdefault("index", object())
    return service.plan(**kwargs)


def paths_at(candidates, tier):
    return [c.path for c in candidates if c.tier == tier]


def tier_of(candidates, path):
    return next(c.tier for c in candidates if c.path == path)


# ============================================================
# TIER 0 — THE DEFECT SITE
# ============================================================

def test_the_defect_site_comes_first():
    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake", 12)],
        },
        ranked=ranked("other/thing.fake"),
    )

    assert plan[0].tier == TIER_DEFECT
    assert plan[0].path == "ui/screen.fake"
    assert plan[0].symbol == "Widget"
    assert plan[0].line == 12


def test_every_candidate_explains_itself():
    """
    `reason` is the only field that answers "why was the model shown
    this?" when a patch comes back wrong.
    """

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        ranked=ranked("ui/screen.fake", "other/thing.fake"),
    )

    assert all(c.reason for c in plan)
    assert "defect site" in plan[0].reason


def test_multiple_defect_symbols_in_one_file_are_all_kept():
    """
    Two declarations in one file are distinct context, unlike two
    file-level reasons for the same file.
    """

    plan = build(
        diagnosis={
            "root_cause_locations": [
                location("First", "core/mod.fake", 3),
                location("Second", "core/mod.fake", 40),
            ],
        },
    )

    assert [c.symbol for c in paths_and_symbols(plan, TIER_DEFECT)] == [
        "First",
        "Second",
    ]


def paths_and_symbols(plan, tier):
    return [c for c in plan if c.tier == tier]


# ============================================================
# FALLBACK WHEN NOTHING RESOLVED
# ============================================================

def test_an_unresolved_defect_falls_back_to_a_cited_file():
    plan = build(
        diagnosis={
            "root_cause_locations": [],
            "relevant_files": ["cited/file.fake"],
        },
        ranked=ranked("ranked/other.fake"),
    )

    assert plan[0].tier == TIER_DEFECT
    assert plan[0].path == "cited/file.fake"
    assert plan[0].symbol is None
    assert "no defect symbol resolved" in plan[0].reason


def test_with_no_diagnosis_at_all_ranking_still_produces_context():
    """
    Retrieval succeeding while the model fails is a normal path. The
    package must still be useful.
    """

    plan = build(ranked=ranked("a.fake", "b.fake"))

    assert plan
    assert plan[0].path == "a.fake"
    assert plan[0].tier == TIER_DEFECT


def test_with_no_inputs_at_all_the_plan_is_empty():
    assert build() == []


# ============================================================
# TIER 2 — DEPENDENCIES
# ============================================================

def test_imports_of_the_defect_are_included():
    graph = RepositoryGraph([
        edge("ui/screen.fake", "core/model.fake"),
        edge("ui/screen.fake", "core/service.fake"),
    ])

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        graph=graph,
    )

    assert set(paths_at(plan, TIER_DEPENDENCY)) == {
        "core/model.fake",
        "core/service.fake",
    }


def test_dependencies_of_unrelated_files_are_not_followed():
    graph = RepositoryGraph([
        edge("other/thing.fake", "core/unrelated.fake"),
    ])

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        graph=graph,
    )

    assert "core/unrelated.fake" not in [c.path for c in plan]


# ============================================================
# TIER 3 — CALLERS
# ============================================================

def test_symbol_references_become_callers():
    code = FakeCodeIntelligence(
        references={
            "Widget": [
                Reference(
                    path="ui/other.fake",
                    symbol="Widget",
                    line=9,
                    kind="state_test",
                )
            ]
        }
    )

    plan = build(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
    )

    caller = next(c for c in plan if c.tier == TIER_CALLER)

    assert caller.path == "ui/other.fake"
    assert "state_test" in caller.reason


def test_a_symbol_reference_outranks_a_bare_import():
    """
    A file that uses the defect's symbol is stronger evidence than one
    that merely imports the file declaring it. Both reach tier 3, but
    the symbol reference must claim the file first so its reason is
    the one recorded.
    """

    code = FakeCodeIntelligence(
        references={
            "Widget": [
                Reference("ui/other.fake", "Widget", 9, "state_test")
            ]
        }
    )

    graph = RepositoryGraph([edge("ui/other.fake", "ui/screen.fake")])

    plan = build(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        graph=graph,
    )

    entries = [c for c in plan if c.path == "ui/other.fake"]

    assert len(entries) == 1
    assert "state_test" in entries[0].reason


# ============================================================
# TIER 4 — CONTRACTS
# ============================================================

@pytest.mark.parametrize(
    "relationship",
    ["implements", "extends", "mixes_in"],
)
def test_contracts_are_followed_in_both_directions(relationship):
    """
    Both the interface the defect satisfies and whatever satisfies the
    defect. A patch that changes a signature must keep both ends
    compiling.
    """

    graph = RepositoryGraph([
        edge("ui/screen.fake", "core/contract.fake", relationship),
        edge("ui/child.fake", "ui/screen.fake", relationship),
    ])

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        graph=graph,
    )

    assert set(paths_at(plan, TIER_CONTRACT)) == {
        "core/contract.fake",
        "ui/child.fake",
    }


def test_a_non_contract_edge_is_not_a_contract():
    graph = RepositoryGraph([
        edge("ui/screen.fake", "core/model.fake", "imports"),
    ])

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        graph=graph,
    )

    assert paths_at(plan, TIER_CONTRACT) == []
    assert paths_at(plan, TIER_DEPENDENCY) == ["core/model.fake"]


# ============================================================
# TIER 5 — TESTS
# ============================================================

def test_a_test_reaching_the_changed_code_is_included():
    code = FakeCodeIntelligence(tests={"spec/screen_spec.fake"})

    graph = RepositoryGraph([
        edge("spec/screen_spec.fake", "ui/screen.fake"),
    ])

    plan = build(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        ranked=ranked("spec/screen_spec.fake"),
        graph=graph,
    )

    assert paths_at(plan, TIER_TEST) == ["spec/screen_spec.fake"]


def test_a_test_never_arrives_in_another_tier():
    """
    A test importing the defect would otherwise be admitted as a
    CALLER before the test tier is reached — over-prioritised, and
    outside the cap the test tier exists to impose.
    """

    code = FakeCodeIntelligence(tests={"spec/screen_spec.fake"})

    graph = RepositoryGraph([
        edge("spec/screen_spec.fake", "ui/screen.fake"),
    ])

    plan = build(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        ranked=ranked("spec/screen_spec.fake"),
        graph=graph,
    )

    entries = [c for c in plan if c.path == "spec/screen_spec.fake"]

    assert len(entries) == 1
    assert entries[0].tier == TIER_TEST


def test_an_unrelated_test_is_not_included():
    """
    Without this every test in the repository qualifies, and the
    package fills with tests for unrelated features.
    """

    code = FakeCodeIntelligence(tests={"spec/unrelated_spec.fake"})

    graph = RepositoryGraph([
        edge("spec/unrelated_spec.fake", "other/thing.fake"),
    ])

    plan = build(
        code=code,
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        ranked=ranked("spec/unrelated_spec.fake"),
        graph=graph,
    )

    assert paths_at(plan, TIER_TEST) == []


# ============================================================
# DEDUPLICATION AND ORDER
# ============================================================

def test_a_file_claimed_by_a_strong_tier_is_not_repeated_weakly():
    graph = RepositoryGraph([
        edge("ui/screen.fake", "core/model.fake"),
    ])

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        ranked=ranked("ui/screen.fake", "core/model.fake"),
        graph=graph,
    )

    assert [c.path for c in plan].count("ui/screen.fake") == 1
    assert [c.path for c in plan].count("core/model.fake") == 1
    assert tier_of(plan, "core/model.fake") == TIER_DEPENDENCY


def test_candidates_are_ordered_by_tier():
    graph = RepositoryGraph([
        edge("ui/screen.fake", "core/model.fake"),
    ])

    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
            "locations": [location("Helper", "core/helper.fake")],
        },
        ranked=ranked("misc/extra.fake"),
        graph=graph,
    )

    tiers = [c.tier for c in plan]

    assert tiers == sorted(tiers)
    assert tiers[0] == TIER_DEFECT
    assert TIER_SUPPORTING in tiers
    assert tiers[-1] == TIER_SECONDARY


def test_the_plan_is_deterministic():
    """
    Snapshot testing the package depends on this, and every input is
    already deterministic.
    """

    graph = RepositoryGraph([
        edge("ui/screen.fake", "core/model.fake"),
        edge("ui/screen.fake", "core/other.fake"),
        edge("ui/a.fake", "ui/screen.fake"),
        edge("ui/b.fake", "ui/screen.fake"),
    ])

    arguments = {
        "diagnosis": {
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        "ranked": ranked("z.fake", "y.fake", "x.fake"),
        "graph": graph,
    }

    first = build(**arguments)
    second = build(**arguments)

    assert first == second


# ============================================================
# DEGRADATION
# ============================================================

def test_no_graph_still_yields_the_defect_and_secondary_tiers():
    plan = build(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        ranked=ranked("misc/extra.fake"),
        graph=None,
    )

    assert paths_at(plan, TIER_DEFECT) == ["ui/screen.fake"]
    assert paths_at(plan, TIER_SECONDARY) == ["misc/extra.fake"]
    assert paths_at(plan, TIER_DEPENDENCY) == []


def test_the_index_is_built_once_from_files():
    code = FakeCodeIntelligence()
    service = ContextBuilderService(code)

    service.plan(
        diagnosis={
            "root_cause_locations": [location("Widget", "ui/screen.fake")],
        },
        files=[{"path": "ui/screen.fake", "content": "whatever"}],
    )

    assert code.index_calls == 1
