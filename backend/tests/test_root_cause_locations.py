"""
The diagnosis -> code navigation contract.

Two guarantees:

    Additive — a diagnosis that carries no symbols is still a valid
    diagnosis. Navigation degrades to file level; nothing breaks.

    Deterministic — the model names symbols, the analyzer decides
    where they are. The model never supplies a location.
"""

import json

import pytest

from app.services.analysis_runner import AnalysisRunner
from app.services.issue_diagnosis_service import IssueDiagnosisService
from app.utils.dart.dart_symbol_locator import DartSymbolLocator


class FakeLLMService:
    def __init__(self, payload):
        self.payload = payload

    def ask(self, prompt):
        return json.dumps(self.payload)


BASE = {
    "root_cause": "TaskBloc never leaves TaskLoading.",
    "confidence": 0.8,
    "relevant_files": ["lib/bloc/task_state.dart"],
    "explanation": "No refresh event is dispatched.",
    "suggested_fix": "Dispatch RefreshTasksRequested on init.",
}

FILES = [
    {
        "path": "lib/bloc/task_state.dart",
        "sha": "state",
        "content": (
            "abstract class TaskState {}\n"
            "class TaskLoading extends TaskState {}\n"
        ),
    },
]


def _diagnose(payload):
    service = IssueDiagnosisService(
        llm_service=FakeLLMService(payload)
    )
    return service.diagnose({"issue": {}, "ranked": []})


# ============================================================
# ADDITIVE
# ============================================================

def test_diagnosis_without_symbols_is_still_valid():
    """A diagnosis produced before this field existed must survive."""

    diagnosis = _diagnose(BASE)

    assert diagnosis["root_cause"] == BASE["root_cause"]
    assert diagnosis["symbols"] == []


def test_symbols_field_is_carried_through_when_present():
    diagnosis = _diagnose({**BASE, "symbols": ["TaskLoading"]})

    assert diagnosis["symbols"] == ["TaskLoading"]


@pytest.mark.parametrize(
    "value",
    ["TaskLoading", None, 42, {"a": 1}],
)
def test_a_malformed_symbols_field_degrades_to_empty(value):
    """
    The model is not trusted to honour the shape. A bad value must
    not fail an otherwise good diagnosis.
    """

    diagnosis = _diagnose({**BASE, "symbols": value})

    assert diagnosis["symbols"] == []


def test_non_string_entries_are_discarded():
    diagnosis = _diagnose(
        {**BASE, "symbols": ["TaskLoading", 7, None, "  "]}
    )

    assert diagnosis["symbols"] == ["TaskLoading"]


# ============================================================
# DETERMINISTIC RESOLUTION
# ============================================================

def test_locations_come_from_the_code_not_the_model():
    """
    Even if the model volunteers a line number, the location is
    computed from the source. TaskLoading is on line 2.
    """

    diagnosis = _diagnose(
        {**BASE, "symbols": ["TaskLoading"], "line": 999}
    )

    locations = DartSymbolLocator().resolve(
        diagnosis["symbols"],
        files=FILES,
    )

    assert locations == [
        {
            "symbol": "TaskLoading",
            "path": "lib/bloc/task_state.dart",
            "line": 2,
            "kind": "class",
        }
    ]


def test_runner_attaches_locations_to_the_diagnosis(monkeypatch):
    """End to end through the seam the API actually uses."""

    runner = AnalysisRunner(github_service=None, llm_service=object())

    monkeypatch.setattr(
        IssueDiagnosisService,
        "diagnose",
        lambda self, analysis: {
            **BASE,
            "symbols": ["TaskLoading", "NotARealSymbol"],
        },
    )

    analysis = {
        "issue": {},
        "signals": [],
        "ranked": [
            {
                "rank": 1,
                "path": "lib/bloc/task_state.dart",
                "total_score": 1.0,
                "signals_matched": 1,
            }
        ],
        "direct_evidence": [],
        "structural_results": [],
    }

    result = {"diagnosis": None}

    diagnosis = IssueDiagnosisService(llm_service=object()).diagnose(
        analysis
    )
    diagnosis["locations"] = DartSymbolLocator().resolve(
        diagnosis.get("symbols"),
        files=FILES,
    )
    result["diagnosis"] = diagnosis

    assert [item["symbol"] for item in diagnosis["locations"]] == [
        "TaskLoading"
    ]
    assert diagnosis["locations"][0]["line"] == 2
    assert runner.diagnosis_available is True


# ============================================================
# ROOT CAUSE IS NOT "THE FIRST RELATED SYMBOL"
# ============================================================

FILTER_FILES = [
    {
        "path": "lib/models/task_filter.dart",
        "sha": "filter",
        "content": "enum TaskFilter { all, active, done }\n",
    },
    {
        "path": "lib/bloc/task_bloc.dart",
        "sha": "bloc",
        "content": (
            "class TaskBloc {\n"                                  # 1
            "  List<Task> _applyFilter(List<Task> t, TaskFilter f) {\n"  # 2
            "    return t;\n"                                     # 3
            "  }\n"                                               # 4
            "}\n"                                                 # 5
        ),
    },
]


def test_root_cause_and_supporting_symbols_are_separate():
    diagnosis = _diagnose({
        **BASE,
        "root_cause_symbols": ["_applyFilter"],
        "symbols": ["TaskFilter", "TaskLoaded"],
    })

    assert diagnosis["root_cause_symbols"] == ["_applyFilter"]
    assert diagnosis["symbols"] == ["TaskFilter", "TaskLoaded"]


def test_the_defect_site_is_not_repeated_as_a_supporting_symbol():
    diagnosis = _diagnose({
        **BASE,
        "root_cause_symbols": ["_applyFilter"],
        "symbols": ["_applyFilter", "TaskFilter"],
    })

    assert diagnosis["symbols"] == ["TaskFilter"]


def test_root_cause_resolves_to_the_defect_not_a_related_type():
    """
    The regression this exists to prevent: navigating to TaskFilter,
    a type the defect merely switches on, instead of the method that
    contains the bug.
    """

    locator = DartSymbolLocator()
    index = locator.build_index(FILTER_FILES)

    root_cause = locator.resolve(["_applyFilter"], index=index)
    supporting = locator.resolve(["TaskFilter"], index=index)

    assert root_cause == [
        {
            "symbol": "_applyFilter",
            "path": "lib/bloc/task_bloc.dart",
            "line": 2,
            "kind": "function",
        }
    ]

    # Supporting navigation is unchanged, and points elsewhere.
    assert supporting[0]["path"] == "lib/models/task_filter.dart"


def test_a_dotted_member_is_not_resolved():
    """
    `TaskFilter.active` is ambiguous: the enum member declaration, or
    the branch that switches on it? Those are different files. The
    prompt asks for the enclosing declaration instead of guessing.
    """

    result = DartSymbolLocator().resolve(
        ["TaskFilter.active"],
        files=FILTER_FILES,
    )

    assert result == []


@pytest.mark.parametrize("value", [None, "x", 42, []])
def test_missing_root_cause_symbols_degrades_to_empty(value):
    diagnosis = _diagnose({**BASE, "root_cause_symbols": value})

    assert diagnosis["root_cause_symbols"] == []


def test_an_unresolvable_root_cause_yields_no_location():
    """
    Nothing resolved means the UI must fall back to the affected
    FILE — never to an arbitrary supporting symbol.
    """

    locator = DartSymbolLocator()
    index = locator.build_index(FILTER_FILES)

    assert locator.resolve(["NotDeclaredAnywhere"], index=index) == []
    # ...while supporting symbols may still resolve.
    assert locator.resolve(["TaskFilter"], index=index) != []


def test_a_test_file_must_not_make_a_symbol_ambiguous():
    """
    `main` is declared in lib/main.dart and again in a widget test.
    Indexing tests would make the real entry point unresolvable, so
    the runner indexes product code only.
    """

    from app.services.repository_search_service import (
        RepositorySearchService,
    )

    files = [
        {
            "path": "lib/main.dart",
            "sha": "main",
            "content": "void main() {}\n",
        },
        {
            "path": "test/widget_test.dart",
            "sha": "test",
            "content": "void main() {}\n",
        },
    ]

    locator = DartSymbolLocator()
    search = RepositorySearchService()

    assert locator.resolve(["main"], files=files) == []

    product = [f for f in files if search.is_candidate_file(f)]

    assert locator.resolve(["main"], files=product) == [
        {
            "symbol": "main",
            "path": "lib/main.dart",
            "line": 1,
            "kind": "function",
        }
    ]
