"""
Tests for PatchGenerator: types, context anchoring, prompt, generate().

No runner or API integration. Default suite uses a fake LLM only.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.code_intelligence.types import (
    BudgetUsage,
    ContextPackage,
    ContextSlice,
    FileRollup,
)
from app.services.patch_context import (
    build_line_map,
    expected_old_text,
    lines_fully_covered,
    normalize_text,
    validate_hunk,
    validate_hunks,
)
from app.services.patch_generator_service import (
    PatchGeneratorService,
    empty_context_proposal,
    invalid_proposal,
)
from app.services.patch_types import (
    PatchFile,
    PatchHunk,
    PatchProposal,
    STATUS_AMBIGUOUS,
    STATUS_EMPTY,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_INVALID,
    STATUS_OK,
)


PATH = "lib/presentation/bloc/task_bloc.fake"
TASK_BLOC = "lib/presentation/bloc/task_bloc.dart"
TASK_REFRESH_FIXTURE = (
    REPO_ROOT
    / "evalutation"
    / "fixtures"
    / "task_refresh_pre_fix.json"
)


class FakeLLMService:
    """Records the prompt and returns a fixed patch JSON string."""

    def __init__(self, response=None):
        self.prompt = None
        self.response = response

    def ask(self, prompt):
        self.prompt = prompt
        return self.response


def patch_json(**overrides):
    payload = {
        "status": STATUS_OK,
        "summary": "emit loaded state after refresh",
        "reasoning": "Refresh handler never leaves TaskLoading.",
        "confidence": 0.9,
        "warnings": [],
        "files": [
            {
                "path": PATH,
                "hunks": [
                    {
                        "start_line": 11,
                        "end_line": 11,
                        "old_text": "line 11",
                        "new_text": "fixed 11",
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


def slice(path=PATH, start=10, end=12, content=None, tier=0):
    if content is None:
        content = "\n".join([
            "line 10",
            "line 11",
            "line 12",
        ])

    return ContextSlice(
        path=path,
        start_line=start,
        end_line=end,
        tier=tier,
        reason="declares Widget, named as the defect site",
        symbols=("Widget",),
        content=content,
        truncated=False,
        language="fake",
        adapter="FakeCodeIntelligence",
    )


def package(*slices, warnings=None, omitted=None):
    return ContextPackage(
        slices=list(slices),
        files=[
            FileRollup(
                path=slices[0].path,
                total_lines=20,
                included_lines=slices[0].line_count,
                complete=False,
            )
        ] if slices else [],
        omitted=omitted or [],
        warnings=warnings or [],
        budget=BudgetUsage(
            max_files=12,
            files_used=1,
            max_lines_total=1200,
            lines_used=slices[0].line_count if slices else 0,
            estimated_tokens=10,
            over_budget=False,
        ),
        language="fake",
        adapter="FakeCodeIntelligence",
        issue={"number": 1, "title": "bug", "body": "it breaks"},
        diagnosis={"root_cause": "Widget stuck"},
        root_cause={
            "symbol": "Widget",
            "path": PATH,
            "line": 11,
            "kind": "thing",
        },
    )


# ============================================================
# TYPES
# ============================================================

def test_patch_proposal_to_json_is_deterministic():
    proposal = PatchProposal(
        status="ok",
        summary="fix refresh",
        reasoning="emit loaded state",
        confidence=0.9,
        files=[
            PatchFile(
                path=PATH,
                language="fake",
                hunks=(
                    PatchHunk(
                        start_line=11,
                        end_line=11,
                        old_text="line 11",
                        new_text="fixed 11",
                    ),
                ),
            )
        ],
        warnings=["note"],
        errors=[],
    )

    assert proposal.to_json() == proposal.to_json()
    assert '"status":"ok"' in proposal.to_json()


def test_empty_context_proposal_uses_insufficient_status():
    proposal = empty_context_proposal("no slices supplied")

    assert proposal.status == STATUS_INSUFFICIENT_CONTEXT
    assert proposal.files == []


# ============================================================
# CONTEXT ANCHORING
# ============================================================

def test_build_line_map_reconstructs_absolute_line_numbers():
    line_map = build_line_map([slice()])

    assert line_map[PATH][10] == "line 10"
    assert line_map[PATH][12] == "line 12"


def test_expected_old_text_matches_slice_content():
    text = expected_old_text(PATH, 10, 12, [slice()])

    assert text == "line 10\nline 11\nline 12"


def test_lines_not_fully_covered_when_gap_between_slices():
    slices = [
        slice(start=10, end=10, content="line 10"),
        slice(start=12, end=12, content="line 12"),
    ]

    assert lines_fully_covered(PATH, 10, 12, slices) is False


def test_validate_hunk_accepts_matching_old_text():
    hunk = PatchHunk(
        start_line=11,
        end_line=11,
        old_text="line 11",
        new_text="fixed 11",
    )

    outcome = validate_hunk(PATH, hunk, [slice()])

    assert outcome.accepted is True


def test_validate_hunk_rejects_old_text_mismatch():
    hunk = PatchHunk(
        start_line=11,
        end_line=11,
        old_text="wrong",
        new_text="fixed 11",
    )

    outcome = validate_hunk(PATH, hunk, [slice()])

    assert outcome.accepted is False
    assert "old_text mismatch" in outcome.error


def test_validate_hunk_rejects_path_not_in_context():
    hunk = PatchHunk(
        start_line=1,
        end_line=1,
        old_text="x",
        new_text="y",
    )

    outcome = validate_hunk("lib/other.fake", hunk, [slice()])

    assert outcome.accepted is False
    assert "path not in context" in outcome.error


def test_validate_hunks_rejects_overlapping_ranges():
    hunks = {
        PATH: [
            PatchHunk(10, 11, "line 10\nline 11", "a\nb"),
            PatchHunk(11, 12, "line 11\nline 12", "c\nd"),
        ]
    }

    result = validate_hunks(hunks, [slice()])

    assert len(result.files) == 1
    assert len(result.files[0].hunks) == 1
    assert result.files[0].hunks[0].start_line == 10
    assert any("overlapping hunks" in error for error in result.errors)


def test_validate_hunks_accepts_non_overlapping_hunks_in_one_file():
    hunks = {
        PATH: [
            PatchHunk(10, 10, "line 10", "fixed 10"),
            PatchHunk(12, 12, "line 12", "fixed 12"),
        ]
    }

    result = validate_hunks(hunks, [slice()])

    assert len(result.files) == 1
    assert len(result.files[0].hunks) == 2
    assert result.errors == []


def test_normalize_text_matches_context_builder_extraction():
    assert normalize_text("a\nb\n") == "a\nb"


# ============================================================
# PROMPT
# ============================================================

def test_prompt_includes_rules_issue_diagnosis_and_slices():
    service = PatchGeneratorService()
    prompt = service.build_prompt(
        issue={"title": "Spinner stuck", "body": "Never loads"},
        diagnosis={
            "root_cause": "TaskBloc stuck loading",
            "confidence": 0.9,
            "explanation": "Refresh never completes",
            "suggested_fix": "emit loaded state",
            "root_cause_locations": [
                {
                    "symbol": "Widget",
                    "path": PATH,
                    "line": 11,
                    "kind": "thing",
                }
            ],
        },
        context_package=package(slice()),
    )

    assert "========== RULES ==========" in prompt
    assert "Spinner stuck" in prompt
    assert "TaskBloc stuck loading" in prompt
    assert "========== CONTEXT SLICES ==========" in prompt
    assert "--- SLICE 1 ---" in prompt
    assert f"PATH: {PATH}" in prompt
    assert "line 11" in prompt
    assert "========== RESPONSE FORMAT ==========" in prompt
    assert "insufficient_context" in prompt


def test_prompt_surfaces_context_warnings_and_omitted_files():
    service = PatchGeneratorService()
    prompt = service.build_prompt(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z", "confidence": 0.5},
        context_package=package(
            slice(),
            warnings=["defect site exceeds budget; included anyway"],
            omitted=[],
        ),
    )

    assert "PACKAGE ROOT CAUSE" in prompt
    assert "defect site exceeds budget" in prompt


def test_prompt_is_byte_identical_for_the_same_inputs():
    service = PatchGeneratorService()
    kwargs = dict(
        issue={"title": "bug", "body": "details"},
        diagnosis={
            "root_cause": "x",
            "confidence": 0.8,
            "explanation": "e",
            "suggested_fix": "f",
        },
        context_package=package(slice()),
    )

    assert service.build_prompt(**kwargs) == service.build_prompt(**kwargs)


def test_prompt_lists_editable_paths_only_from_slices():
    service = PatchGeneratorService()
    prompt = service.build_prompt(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(
            slice(path="lib/a.fake", start=1, end=2, content="a\nb"),
            slice(path="lib/b.fake", start=3, end=4, content="c\nd"),
        ),
    )

    assert "Editable paths" in prompt
    assert "lib/a.fake" in prompt
    assert "lib/b.fake" in prompt
    assert "RepositorySearchService" not in prompt
    assert "ranked" not in prompt.lower() or "Do not search" in prompt


def test_validate_proposal_hunks_delegates_to_context_anchoring():
    service = PatchGeneratorService()
    hunks = {
        PATH: [
            PatchHunk(11, 11, "line 11", "fixed 11"),
        ]
    }

    result = service.validate_proposal_hunks(hunks, package(slice()))

    assert len(result.files) == 1
    assert result.files[0].path == PATH


# ============================================================
# GENERATE()
# ============================================================

def test_generate_skips_llm_when_context_is_empty():
    service = PatchGeneratorService(llm_service=FakeLLMService("{}"))
    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(),
    )

    assert proposal.status == STATUS_INSUFFICIENT_CONTEXT
    assert service.llm.prompt is None


def test_generate_returns_invalid_when_llm_is_not_configured():
    service = PatchGeneratorService()
    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_INVALID
    assert "not configured" in proposal.errors[0]


def test_generate_happy_path_accepts_matching_hunk():
    llm = FakeLLMService(patch_json())
    service = PatchGeneratorService(llm_service=llm)
    proposal = service.generate(
        issue={"title": "bug", "body": "details"},
        diagnosis={"root_cause": "Widget stuck", "confidence": 0.9},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_OK
    assert len(proposal.files) == 1
    assert proposal.files[0].hunks[0].new_text == "fixed 11"
    assert proposal.errors == []
    assert llm.prompt is not None
    assert "========== CONTEXT SLICES ==========" in llm.prompt


def test_generate_rejects_mismatched_old_text():
    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            patch_json(
                files=[
                    {
                        "path": PATH,
                        "hunks": [
                            {
                                "start_line": 11,
                                "end_line": 11,
                                "old_text": "wrong",
                                "new_text": "fixed 11",
                            }
                        ],
                    }
                ]
            )
        )
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_EMPTY
    assert proposal.files == []
    assert any("old_text mismatch" in error for error in proposal.errors)


def test_generate_rejects_path_not_in_context():
    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            patch_json(
                files=[
                    {
                        "path": "lib/other.fake",
                        "hunks": [
                            {
                                "start_line": 1,
                                "end_line": 1,
                                "old_text": "x",
                                "new_text": "y",
                            }
                        ],
                    }
                ]
            )
        )
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_EMPTY
    assert any("path not in context" in error for error in proposal.errors)


def test_generate_honors_insufficient_context_refusal():
    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            json.dumps({
                "status": STATUS_INSUFFICIENT_CONTEXT,
                "summary": "cannot patch safely",
                "reasoning": "refresh handler not shown",
                "confidence": None,
                "warnings": ["missing handler body"],
                "files": [],
            })
        )
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_INSUFFICIENT_CONTEXT
    assert proposal.files == []
    assert proposal.warnings == ["missing handler body"]


def test_generate_honors_ambiguous_refusal():
    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            json.dumps({
                "status": STATUS_AMBIGUOUS,
                "summary": "unclear target",
                "reasoning": "multiple handlers match",
                "confidence": None,
                "warnings": [],
                "files": [],
            })
        )
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_AMBIGUOUS
    assert proposal.files == []


def test_generate_malformed_json_returns_invalid():
    service = PatchGeneratorService(
        llm_service=FakeLLMService("not json")
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_INVALID
    assert "not valid JSON" in proposal.errors[0]


def test_generate_strips_markdown_fences_before_parsing():
    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            "```json\n" + patch_json() + "\n```"
        )
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(slice()),
    )

    assert proposal.status == STATUS_OK


def test_generate_accepts_multi_file_proposal():
    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            patch_json(
                files=[
                    {
                        "path": "lib/a.fake",
                        "hunks": [
                            {
                                "start_line": 1,
                                "end_line": 1,
                                "old_text": "a",
                                "new_text": "A",
                            }
                        ],
                    },
                    {
                        "path": "lib/b.fake",
                        "hunks": [
                            {
                                "start_line": 3,
                                "end_line": 3,
                                "old_text": "c",
                                "new_text": "C",
                            }
                        ],
                    },
                ]
            )
        )
    )

    proposal = service.generate(
        issue={"title": "x", "body": "y"},
        diagnosis={"root_cause": "z"},
        context_package=package(
            slice(
                path="lib/a.fake",
                start=1,
                end=2,
                content="a\nb",
            ),
            slice(
                path="lib/b.fake",
                start=3,
                end=4,
                content="c\nd",
            ),
        ),
    )

    assert proposal.status == STATUS_OK
    assert [file.path for file in proposal.files] == [
        "lib/a.fake",
        "lib/b.fake",
    ]


def test_generate_is_byte_identical_for_same_inputs():
    llm = FakeLLMService(patch_json())
    service = PatchGeneratorService(llm_service=llm)
    kwargs = dict(
        issue={"title": "bug", "body": "details"},
        diagnosis={"root_cause": "Widget stuck"},
        context_package=package(slice()),
    )

    first = service.generate(**kwargs)
    second = service.generate(**kwargs)

    assert first.to_json() == second.to_json()


def test_invalid_proposal_helper_uses_invalid_status():
    proposal = invalid_proposal("bad schema")

    assert proposal.status == STATUS_INVALID
    assert proposal.errors == ["bad schema"]


# ============================================================
# TASK REFRESH FIXTURE DEMO
# ============================================================

def _task_refresh_slice():
    snapshot = json.loads(TASK_REFRESH_FIXTURE.read_text())
    content = next(
        item["content"]
        for item in snapshot["files"]
        if item["path"] == TASK_BLOC
    )
    lines = content.splitlines()
    start = 55
    end = 58
    snippet = "\n".join(lines[start - 1:end])

    return ContextSlice(
        path=TASK_BLOC,
        start_line=start,
        end_line=end,
        tier=0,
        reason="declares TaskBloc, named as the defect site",
        symbols=("TaskBloc",),
        content=snippet,
        truncated=False,
        language="dart",
        adapter="DartCodeIntelligence",
    )


def test_task_refresh_fixture_accepts_known_fix_hunk():
    task_slice = _task_refresh_slice()
    old_text = (
        "      case Success(data: final tasks):\n"
        "        // Update the cached filter before handing the results back to the UI.\n"
        "        _currentFilter = _currentFilter;\n"
        "        break;"
    )
    new_text = (
        "      case Success(data: final tasks):\n"
        "        emit(TaskLoaded(tasks: tasks, filter: _currentFilter));\n"
        "        break;"
    )

    service = PatchGeneratorService(
        llm_service=FakeLLMService(
            patch_json(
                files=[
                    {
                        "path": TASK_BLOC,
                        "hunks": [
                            {
                                "start_line": 55,
                                "end_line": 58,
                                "old_text": old_text,
                                "new_text": new_text,
                            }
                        ],
                    }
                ]
            )
        )
    )

    proposal = service.generate(
        issue={
            "title": "Task list stuck on the loading spinner",
            "body": "Refresh never leaves the spinner.",
        },
        diagnosis={
            "root_cause": "TaskBloc never emits TaskLoaded on refresh.",
            "confidence": 0.9,
            "explanation": "Refresh handler stops in TaskLoading.",
            "suggested_fix": "emit(TaskLoaded) after refresh succeeds.",
            "root_cause_locations": [
                {
                    "symbol": "TaskBloc",
                    "path": TASK_BLOC,
                    "line": 47,
                    "kind": "class",
                }
            ],
        },
        context_package=ContextPackage(
            slices=[task_slice],
            files=[],
            omitted=[],
            warnings=[],
            budget=BudgetUsage(
                max_files=12,
                files_used=1,
                max_lines_total=1200,
                lines_used=task_slice.line_count,
                estimated_tokens=10,
                over_budget=False,
            ),
            language="dart",
            adapter="DartCodeIntelligence",
            issue={"number": 1},
            diagnosis={"root_cause": "TaskBloc never emits TaskLoaded"},
            root_cause={
                "symbol": "TaskBloc",
                "path": TASK_BLOC,
                "line": 47,
                "kind": "class",
            },
        ),
    )

    assert proposal.status == STATUS_OK
    assert proposal.files[0].path == TASK_BLOC
    assert "emit(TaskLoaded" in proposal.files[0].hunks[0].new_text
    assert proposal.errors == []
