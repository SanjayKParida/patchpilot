"""
Tests for the commit-grounded benchmark runner.

Deterministic and offline. The runner exists to measure the pipeline,
so its own scoring must be beyond doubt — a benchmark with a buggy
scorer is worse than no benchmark, because it produces numbers.

The real Issue #1 pre-fix fixture is used, but the language model and
GitHub are both faked: the normal suite must never call either.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evalutation.commit_benchmark import (  # noqa: E402
    BenchmarkError,
    discover_cases,
    is_diagnosis_correct,
    load_case,
    load_snapshot,
    report_rollup,
    run_all,
    run_case,
    score_concepts,
    score_files,
    summarize,
    worst_rank,
)

FIXTURE = (
    REPO_ROOT
    / "evalutation"
    / "fixtures"
    / "task_refresh_pre_fix.json"
)

FIX_COMMIT = "afd804edc491fb08e2bb2eed9df4bbfc6985edca"
PARENT = "d8e50b735c78620103b1ab031dcd9070c123a785"

TASK_BLOC = "lib/presentation/bloc/task_bloc.dart"


def _case(tmp_path, **overrides):
    case = {
        "owner": "SanjayKParida",
        "repo": "patchpilot-diagnosis-demo",
        "issue_number": 1,
        "fix_commit": FIX_COMMIT,
        "snapshot": str(FIXTURE),
        "title": "Task list stuck on the loading spinner",
        "body": "Refreshing never leaves the spinner.",
        "signals": [
            {"term": "refresh", "type": "behavior"},
            {"term": "loading", "type": "behavior"},
            {"term": "task", "type": "domain"},
        ],
    }
    case.update(overrides)

    path = Path(tmp_path)
    path.mkdir(parents=True, exist_ok=True)
    path = path / "case.json"
    path.write_text(json.dumps(case))

    return path


class FakeGithub:
    """Serves the real Issue #1 fix diff without touching the network."""

    def get_commit(self, owner, repo, ref):
        return {"sha": FIX_COMMIT, "parents": [{"sha": PARENT}]}

    def compare_commits(self, owner, repo, base, head):
        return {
            "files": [
                {"filename": TASK_BLOC, "status": "modified"},
                {
                    "filename": "test/presentation/bloc/task_bloc_test.dart",
                    "status": "modified",
                },
            ]
        }


class FakeLLM:
    """
    Answers both prompts the pipeline makes.

    Signal extraction and diagnosis are separate model calls with
    different response shapes, so a single canned payload fails
    validation on one of them. Keyed off the diagnosis prompt's
    required field.
    """

    available = True

    EXTRACTED_SIGNALS = {
        "signals": [
            {"term": "task", "type": "domain"},
            {"term": "spinner", "type": "behavior"},
        ]
    }

    def __init__(self, payload=None):
        self.payload = payload or {
            "root_cause": (
                "TaskBloc handles RefreshTasksRequested but never "
                "emits TaskLoaded, so it remains in TaskLoading."
            ),
            "confidence": 0.9,
            "relevant_files": [TASK_BLOC],
            "root_cause_symbols": ["TaskBloc"],
            "symbols": ["TaskLoading"],
            "explanation": "The handler emits TaskLoading and stops.",
            "suggested_fix": "emit(TaskLoaded(tasks)) after loading.",
        }

    def ask(self, prompt):
        if "root_cause" not in prompt:
            return json.dumps(self.EXTRACTED_SIGNALS)

        return json.dumps(self.payload)


# ============================================================
# CASE LOADING
# ============================================================

def test_a_valid_case_loads(tmp_path):
    case = load_case(_case(tmp_path))

    assert case["issue_number"] == 1
    assert case["fix_commit"] == FIX_COMMIT
    assert case["_path"].endswith("case.json")


@pytest.mark.parametrize(
    "field",
    ["owner", "repo", "issue_number", "fix_commit", "snapshot"],
)
def test_a_case_missing_a_required_field_is_refused(tmp_path, field):
    """
    Validated up front. Discovering a missing fix commit after paying
    for two model calls is pure waste.
    """

    path = _case(tmp_path, **{field: None})

    with pytest.raises(BenchmarkError, match=field):
        load_case(path)


def test_a_missing_case_file_is_refused(tmp_path):
    with pytest.raises(BenchmarkError, match="No case file"):
        load_case(tmp_path / "nope.json")


def test_malformed_json_is_refused(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")

    with pytest.raises(BenchmarkError, match="not valid JSON"):
        load_case(path)


def test_the_issue_one_snapshot_loads(tmp_path):
    snapshot = load_snapshot(load_case(_case(tmp_path)))

    assert snapshot["commit"] == PARENT
    assert snapshot["issue"]["number"] == 1
    assert any(f["path"] == TASK_BLOC for f in snapshot["files"])


def test_a_missing_snapshot_is_refused(tmp_path):
    case = load_case(_case(tmp_path, snapshot="nowhere.json"))

    with pytest.raises(BenchmarkError, match="No snapshot"):
        load_snapshot(case)


# ============================================================
# FILE SCORING
# ============================================================

RANKED = [
    {"rank": 1, "path": "lib/presentation/pages/task_list_page.dart"},
    {"rank": 2, "path": TASK_BLOC},
    {"rank": 3, "path": "lib/presentation/bloc/task_state.dart"},
]


def test_a_correct_prediction_scores_perfectly():
    score = score_files([TASK_BLOC], [TASK_BLOC], RANKED)

    assert score["recall"] == 1.0
    assert score["precision"] == 1.0
    assert score["hits"] == [TASK_BLOC]
    assert score["missed"] == []


def test_a_wrong_prediction_scores_zero():
    score = score_files([TASK_BLOC], ["lib/other.dart"], RANKED)

    assert score["recall"] == 0.0
    assert score["precision"] == 0.0
    assert score["missed"] == [TASK_BLOC]


def test_extra_predictions_cost_precision_not_recall():
    score = score_files(
        [TASK_BLOC],
        [TASK_BLOC, "lib/other.dart"],
        RANKED,
    )

    assert score["recall"] == 1.0
    assert score["precision"] == 0.5


def test_rank_of_the_expected_file_is_reported():
    score = score_files([TASK_BLOC], [], RANKED)

    assert score["rank_of_expected"][TASK_BLOC] == 2


def test_an_unranked_expected_file_reports_no_rank():
    score = score_files(["lib/never.dart"], [], RANKED)

    assert score["rank_of_expected"]["lib/never.dart"] is None


def test_recall_at_k_reflects_where_the_file_landed():
    score = score_files([TASK_BLOC], [], RANKED)

    # Ranked #2, so absent from top-1 and present from top-3 on.
    assert score["recall_at"][1] == 0.0
    assert score["recall_at"][3] == 1.0
    assert score["recall_at"][10] == 1.0


def test_empty_ground_truth_does_not_divide_by_zero():
    score = score_files([], [TASK_BLOC], RANKED)

    assert score["recall"] == 0.0
    assert score["precision"] == 0.0


# ============================================================
# CONCEPT SCORING
# ============================================================

def test_any_alternative_in_a_group_satisfies_it():
    groups = [["TaskLoaded", "emit(TaskLoaded", "remains in TaskLoading"]]

    assert score_concepts(groups, "it never emits TaskLoaded")["score"] == 1.0
    assert score_concepts(groups, "remains in TaskLoading")["score"] == 1.0


def test_partial_concept_coverage_is_partial_credit():
    groups = [["RefreshTasksRequested"], ["TaskLoading"], ["TaskLoaded"]]

    score = score_concepts(groups, "TaskLoading is never replaced")

    assert score["score"] == pytest.approx(1 / 3)
    assert score["missed"] == [["RefreshTasksRequested"], ["TaskLoaded"]]


def test_concept_matching_ignores_case():
    assert score_concepts([["TaskLoaded"]], "taskloaded")["score"] == 1.0


def test_no_ground_truth_concepts_means_no_score():
    assert score_concepts(None, "anything") is None
    assert score_concepts([], "anything") is None


# ============================================================
# END TO END, OFFLINE
# ============================================================

def test_run_case_scores_the_real_issue_one_fixture(tmp_path):
    """
    The whole runner over the real pre-fix snapshot, with the model
    and GitHub faked. Proves the orchestration and scoring agree.
    """

    case = load_case(
        _case(
            tmp_path,
            diagnosis_ground_truth={
                "mechanism_concepts": [
                    ["RefreshTasksRequested"],
                    ["TaskLoading"],
                ],
                "fix_concepts": [["emit(TaskLoaded", "TaskLoaded"]],
            },
        )
    )

    result = run_case(case, github=FakeGithub(), llm=FakeLLM())

    # Ground truth came from the fix diff, with the test file dropped.
    assert result["ground_truth"]["affected_files"] == [TASK_BLOC]
    assert result["files"]["expected"] == [TASK_BLOC]

    # The faked diagnosis cited the right file.
    assert result["files"]["recall"] == 1.0
    assert result["files"]["precision"] == 1.0

    # Retrieval actually ranked it.
    assert result["files"]["rank_of_expected"][TASK_BLOC] is not None

    # Concept scoring read the diagnosis prose.
    assert result["mechanism"]["score"] == 1.0
    assert result["fix"]["score"] == 1.0

    # Symbols resolved deterministically through the production path.
    locations = result["diagnosis"]["root_cause_locations"]
    assert [item["symbol"] for item in locations] == ["TaskBloc"]
    assert locations[0]["path"] == TASK_BLOC

    assert result["snapshot_commit"] == result["parent_commit"]


def test_a_missed_file_is_reported_as_missed(tmp_path):
    case = load_case(_case(tmp_path))

    llm = FakeLLM({
        "root_cause": "Something unrelated.",
        "confidence": 0.4,
        "relevant_files": ["lib/presentation/pages/task_list_page.dart"],
        "explanation": "...",
        "suggested_fix": "...",
    })

    result = run_case(case, github=FakeGithub(), llm=llm)

    assert result["files"]["recall"] == 0.0
    assert result["files"]["missed"] == [TASK_BLOC]
    assert result["mechanism"] is None


# ============================================================
# ROLLUP: CORRECTNESS
# ============================================================

def _files(recall=1.0, precision=1.0, expected=(TASK_BLOC,), ranks=None):
    return {
        "expected": list(expected),
        "predicted": [],
        "hits": [],
        "missed": [],
        "recall": recall,
        "precision": precision,
        "rank_of_expected": (
            ranks if ranks is not None else {TASK_BLOC: 1}
        ),
        "recall_at": {1: 1.0, 3: 1.0, 5: 1.0, 10: 1.0},
    }


def test_a_diagnosis_that_found_everything_passes():
    assert is_diagnosis_correct(_files(recall=1.0), None) is True


def test_a_diagnosis_that_missed_a_file_fails():
    assert is_diagnosis_correct(_files(recall=0.5), None) is False


def test_the_right_file_for_the_wrong_reason_fails():
    """Precision alone is not correctness."""

    mechanism = {"score": 0.0, "matched": [], "missed": [["X"]]}

    assert is_diagnosis_correct(_files(recall=1.0), mechanism) is False


def test_a_partly_understood_mechanism_can_still_pass():
    mechanism = {"score": 0.5, "matched": ["X"], "missed": []}

    assert is_diagnosis_correct(_files(recall=1.0), mechanism) is True


def test_a_case_with_no_ground_truth_files_cannot_pass():
    assert is_diagnosis_correct(_files(expected=()), None) is False


# ============================================================
# ROLLUP: WORST RANK
# ============================================================

def test_worst_rank_reports_the_deepest_expected_file():
    """
    With two expected files, reporting the one at #1 would hide the
    one buried at #9.
    """

    assert worst_rank(_files(ranks={"a": 1, "b": 9})) == 9


def test_worst_rank_is_none_when_a_file_never_ranked():
    assert worst_rank(_files(ranks={"a": 1, "b": None})) is None


def test_worst_rank_is_none_when_nothing_was_expected():
    assert worst_rank(_files(ranks={})) is None


# ============================================================
# ROLLUP: AGGREGATION
# ============================================================

def _result(number, recall=1.0, precision=1.0, correct=True,
            recall_at=None, mechanism=None):
    return {
        "case": f"case{number}.json",
        "correct": correct,
        "worst_rank": 1,
        "issue": {"number": number, "title": f"Issue {number}"},
        "files": {
            **_files(recall=recall, precision=precision),
            "recall_at": recall_at
            or {1: 1.0, 3: 1.0, 5: 1.0, 10: 1.0},
        },
        "mechanism": mechanism,
    }


def test_means_are_taken_over_scored_cases():
    aggregate = summarize([
        _result(1, precision=1.0),
        _result(2, precision=0.5),
    ])

    assert aggregate["scored"] == 2
    assert aggregate["precision"] == 0.75


def test_diagnosis_passes_are_counted():
    aggregate = summarize([
        _result(1, correct=True),
        _result(2, correct=False),
        _result(3, correct=True),
    ])

    assert aggregate["diagnosis_passed"] == 2
    assert aggregate["scored"] == 3


def test_recall_at_k_is_averaged_per_k():
    aggregate = summarize([
        _result(1, recall_at={1: 1.0, 3: 1.0, 5: 1.0, 10: 1.0}),
        _result(2, recall_at={1: 0.0, 3: 1.0, 5: 1.0, 10: 1.0}),
    ])

    assert aggregate["recall_at"][1] == 0.5
    assert aggregate["recall_at"][3] == 1.0


def test_a_failed_case_is_counted_but_not_averaged():
    """
    "Could not measure" and "measured, and it was wrong" are
    different facts. Scoring a crash as zero hides the first.
    """

    aggregate = summarize([
        _result(1, precision=1.0),
        {"case": "c2.json", "failed": True, "error": "boom"},
    ])

    assert aggregate["cases"] == 2
    assert aggregate["scored"] == 1
    assert aggregate["failed"] == 1
    assert aggregate["precision"] == 1.0


def test_summarizing_nothing_does_not_divide_by_zero():
    aggregate = summarize([])

    assert aggregate["scored"] == 0
    assert aggregate["precision"] == 0.0
    assert aggregate["recall_at"][1] == 0.0


def test_mechanism_mean_ignores_cases_without_concepts():
    aggregate = summarize([
        _result(1, mechanism={"score": 1.0}),
        _result(2, mechanism=None),
    ])

    assert aggregate["mechanism"] == 1.0


# ============================================================
# ROLLUP: EXECUTION AND FORMATTING
# ============================================================

def test_one_broken_case_does_not_abort_the_run(tmp_path, capsys):
    good = _case(tmp_path)

    bad = tmp_path / "bad.json"
    bad.write_text('{"owner": "o"}')

    results = run_all(
        [good, bad],
        github=FakeGithub(),
        llm=FakeLLM(),
    )

    assert len(results) == 2
    assert results[0]["correct"] is True
    assert results[1]["failed"] is True


def test_the_summary_table_reports_every_column(capsys):
    results = [
        _result(1, precision=1.0, correct=True),
        _result(2, precision=0.5, correct=False),
    ]

    report_rollup(results, summarize(results))

    out = capsys.readouterr().out

    assert "ISSUE" in out and "RANK" in out and "PREC" in out
    assert "@1" in out and "@10" in out
    assert "Issue 1" in out and "Issue 2" in out
    assert "PASS" in out and "FAIL" in out
    assert "diagnosis passed : 1/2" in out


def test_the_summary_names_failed_cases(capsys):
    results = [
        _result(1),
        {"case": "cases/broken.json", "failed": True, "error": "boom"},
    ]

    report_rollup(results, summarize(results))

    out = capsys.readouterr().out

    assert "broken" in out
    assert "FAILED" in out
    assert "cases not scored : 1" in out


# ============================================================
# CASE DIRECTORY DISCOVERY
# ============================================================

def test_every_json_file_in_the_directory_is_discovered(tmp_path):
    for name in ("b.json", "a.json", "c.json"):
        (tmp_path / name).write_text("{}")

    found = discover_cases(tmp_path)

    assert [path.name for path in found] == [
        "a.json",
        "b.json",
        "c.json",
    ]


def test_discovery_is_ordered_by_filename(tmp_path):
    """
    Sorted so a rollup is reproducible. An unordered listing makes two
    runs of the same suite print rows in different orders, which makes
    diffing results needlessly hard.
    """

    for name in ("03_c.json", "01_a.json", "02_b.json"):
        (tmp_path / name).write_text("{}")

    assert [path.name for path in discover_cases(tmp_path)] == [
        "01_a.json",
        "02_b.json",
        "03_c.json",
    ]


def test_non_json_files_are_ignored(tmp_path):
    (tmp_path / "case.json").write_text("{}")
    (tmp_path / "README.md").write_text("notes")
    (tmp_path / "notes.txt").write_text("notes")

    assert [path.name for path in discover_cases(tmp_path)] == [
        "case.json"
    ]


def test_a_missing_directory_is_refused(tmp_path):
    with pytest.raises(BenchmarkError, match="No case directory"):
        discover_cases(tmp_path / "nowhere")


def test_a_file_given_instead_of_a_directory_is_refused(tmp_path):
    path = tmp_path / "case.json"
    path.write_text("{}")

    with pytest.raises(BenchmarkError, match="not a directory"):
        discover_cases(path)


def test_an_empty_directory_is_refused(tmp_path):
    """
    Silently scoring zero cases would report a meaningless 0/0 pass
    rate as if it were a result.
    """

    with pytest.raises(BenchmarkError, match="no .json case files"):
        discover_cases(tmp_path)


def test_a_directory_of_only_non_cases_is_refused(tmp_path):
    (tmp_path / "README.md").write_text("notes")

    with pytest.raises(BenchmarkError, match="no .json case files"):
        discover_cases(tmp_path)


def test_a_relative_directory_resolves_against_the_repo_root():
    found = discover_cases("evalutation/cases/commit_grounded")

    assert [path.name for path in found] == [
        "active_filter.json",
        "empty_state.json",
        "task_refresh.json",
    ]


def test_discovered_cases_all_load(tmp_path):
    """Discovery feeds load_case, so what it returns must be loadable."""

    for path in discover_cases("evalutation/cases/commit_grounded"):
        case = load_case(path)
        assert case["fix_commit"]
        assert case["issue_number"]


def test_a_discovered_directory_runs_end_to_end(tmp_path):
    """
    Discovery and the rollup meet here: point at a directory, get one
    result per file, in filename order.
    """

    for index, name in enumerate(("b_case.json", "a_case.json"), 1):
        source = json.loads(_case(tmp_path / f"src{index}").read_text())
        (tmp_path / name).write_text(json.dumps(source))

    results = run_all(
        discover_cases(tmp_path),
        github=FakeGithub(),
        llm=FakeLLM(),
    )

    assert len(results) == 2
    assert [Path(r["case"]).name for r in results] == [
        "a_case.json",
        "b_case.json",
    ]
    assert all(r["correct"] for r in results)


# ============================================================
# REPRODUCIBILITY
# ============================================================

PINNED = [
    {"term": "refresh", "type": "behavior"},
    {"term": "loading", "type": "behavior"},
]


class RecordingLLM(FakeLLM):
    """Notices if signal extraction was invoked."""

    def __init__(self, payload=None):
        super().__init__(payload)
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return super().ask(prompt)


def test_pinned_signals_are_used_verbatim(tmp_path):
    case = load_case(_case(tmp_path, signals=PINNED))

    result = run_case(case, github=FakeGithub(), llm=FakeLLM())

    assert result["signals"] == PINNED
    assert result["signals_pinned"] is True


def test_pinned_signals_make_ranking_reproducible(tmp_path):
    """
    The property the whole change exists for: identical input,
    identical ranking. Without it, the same case measured rank 3, 1, 1
    on three runs.
    """

    case = load_case(_case(tmp_path, signals=PINNED))

    first = run_case(case, github=FakeGithub(), llm=FakeLLM())
    second = run_case(case, github=FakeGithub(), llm=FakeLLM())

    assert first["ranked"] == second["ranked"]
    assert first["files"]["recall_at"] == second["files"]["recall_at"]
    assert first["worst_rank"] == second["worst_rank"]


def test_extract_signals_bypasses_the_pinned_set(tmp_path):
    case = load_case(_case(tmp_path, signals=PINNED))

    result = run_case(
        case,
        github=FakeGithub(),
        llm=FakeLLM(),
        extract_signals=True,
    )

    assert result["signals_pinned"] is False
    # The extractor ran, so the pinned terms are not what came back.
    assert result["signals"] != PINNED


def test_a_case_without_pinned_signals_is_marked_unpinned(tmp_path):
    case = load_case(_case(tmp_path))
    case.pop("signals", None)

    result = run_case(case, github=FakeGithub(), llm=FakeLLM())

    assert result["signals_pinned"] is False


def test_extract_signals_flows_through_the_rollup(tmp_path):
    path = _case(tmp_path, signals=PINNED)

    pinned = run_all([path], github=FakeGithub(), llm=FakeLLM())
    live = run_all(
        [path],
        github=FakeGithub(),
        llm=FakeLLM(),
        extract_signals=True,
    )

    assert pinned[0]["signals_pinned"] is True
    assert live[0]["signals_pinned"] is False


def test_the_aggregate_counts_pinned_cases():
    aggregate = summarize([
        {**_result(1), "signals_pinned": True},
        {**_result(2), "signals_pinned": False},
    ])

    assert aggregate["signals_pinned"] == 1
    assert aggregate["scored"] == 2


def test_a_fully_pinned_rollup_says_what_is_reproducible(capsys):
    results = [{**_result(1), "signals_pinned": True}]

    report_rollup(results, summarize(results))

    out = capsys.readouterr().out

    assert "RANK and @k are reproducible" in out
    assert "PREC and DIAG" in out


def test_an_unpinned_rollup_warns_loudly(capsys):
    """
    A reader comparing two unpinned runs would be reading noise. Say
    so rather than printing a table that looks authoritative.
    """

    results = [
        {**_result(1), "signals_pinned": True},
        {**_result(2), "signals_pinned": False},
    ]

    report_rollup(results, summarize(results))

    out = capsys.readouterr().out

    assert "WARNING" in out
    assert "No metric in this table is reproducible" in out
    assert "before/after" in out


def test_the_committed_cases_all_pin_their_signals():
    """
    Every commit-grounded case must be reproducible by default, or
    the suite silently stops being a measurement instrument.
    """

    for path in discover_cases("evalutation/cases/commit_grounded"):
        case = load_case(path)

        assert case.get("signals"), f"{path.name} has no pinned signals"
        assert case.get("signals_note"), (
            f"{path.name} pins signals without explaining why"
        )
