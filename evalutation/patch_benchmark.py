"""
Commit-grounded patch repair benchmark.

Measures whether PatchPilot can produce a patch that actually applies
to the pre-fix tree and survives validation — not whether it reproduces
the historical commit.

    pre-fix snapshot -> analysis -> diagnosis -> ContextBuilder
                     -> PatchGenerator -> PatchValidator -> scored

This module orchestrates and scores. It does not rank, diagnose, build
context, generate patches, or validate them; every one of those is an
existing production service, used unmodified.

The evaluation rule that matters
--------------------------------

A patch is NOT wrong for differing from the historical fix. There are
many correct ways to fix a bug, and a benchmark that demands one of
them measures mimicry rather than repair.

The success condition is therefore:

    the generated patch applies cleanly to the pre-fix snapshot
    AND configured validation passes

The fix commit supplies supporting ground truth only: which product
files a real fix had to touch, and which lines it changed. Those drive
recall and precision, which are diagnostics — not the verdict.

Usage
-----

    PYTHONPATH=backend python -m evalutation.patch_benchmark \\
        --cases evalutation/cases/commit_grounded --proposals canned

    PYTHONPATH=backend python -m evalutation.patch_benchmark \\
        --cases evalutation/cases/commit_grounded --proposals generated

    PYTHONPATH=backend python -m evalutation.patch_benchmark \\
        --case evalutation/cases/commit_grounded/task_refresh.json --json

    PYTHONPATH=backend python3 -m evalutation.patch_benchmark \\
        --case evalutation/cases/commit_grounded/task_refresh.json \\
        --snapshot /tmp/task_refresh_full.json \\
        --validation shell

Proposal sources
----------------

    canned      hand-written known-good proposals from
                backend/tests/fixtures/patch_proposals. These exercise
                the apply and validate path with the generator held
                fixed, so a failure is unambiguously downstream.

    generated   real PatchGeneratorService output. This measures the
                repair pipeline. It needs a model and is not
                reproducible run to run.

The two are never mixed in one run, and every result records which was
used. A canned pass says the validator works; only a generated pass
says PatchPilot repaired anything.

Validation profiles
-------------------

The snapshotter stores UTF-8 git blobs with no language include-list.
Whether that tree is a runnable Flutter project is decided by
`FlutterValidationProfile`: it requires `pubspec.yaml` at the repo root
and, when present, supplies `flutter pub get` / `analyze` / `test`.

Committed demo fixtures are still source-only until they are
re-snapshotted. Against those trees the profile reports not runnable
and the harness runs no commands — including the fake runner, so a
PASS cannot be mistaken for a compile check.

    fake    Flutter argv via the deterministic fake runner, only when
            the profile says the tree is runnable.

    none    no commands. The validator warns and reports applied-only.

    shell   real execution via ShellValidationCommandRunner, only when
            runnable. Otherwise commands are skipped and the reason is
            recorded.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.services.github_service import GithubService
from app.services.llm_service import LLMService
from app.services.patch_generator_service import PatchGeneratorService
from app.services.patch_types import (
    STATUS_OK,
    PatchFile,
    PatchHunk,
    PatchProposal,
)
from app.services.patch_validation_types import (
    STATUS_APPLY_FAILED,
    STATUS_PASSED,
    STATUS_PROPOSAL_INVALID,
    STATUS_VALIDATION_FAILED,
    ValidationConfig,
)
from app.services.patch_validator_service import PatchValidatorService
from app.services.validation_command_runner import (
    FakeValidationCommandRunner,
    ShellValidationCommandRunner,
)
from app.services.validation_profiles import FlutterValidationProfile

from evalutation.commit_benchmark import (
    BenchmarkError,
    discover_cases,
    load_case,
    load_snapshot,
)
from evalutation.context_benchmark import (
    build_context_package,
    prepare_case,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKEND_ENV = REPO_ROOT / "backend" / ".env"

CANNED_PROPOSALS = (
    REPO_ROOT / "backend" / "tests" / "fixtures" / "patch_proposals"
)

SOURCE_CANNED = "canned"
SOURCE_GENERATED = "generated"

# Ordered worst to best. A run is summarized by how far each case got.
STAGE_GENERATION_FAILURE = "generation_failure"
STAGE_PROPOSAL_INVALID = "proposal_invalid"
STAGE_APPLY_FAILURE = "apply_failure"
STAGE_VALIDATION_FAILURE = "validation_failure"
STAGE_PASSED = "passed"

STAGES = (
    STAGE_GENERATION_FAILURE,
    STAGE_PROPOSAL_INVALID,
    STAGE_APPLY_FAILURE,
    STAGE_VALIDATION_FAILURE,
    STAGE_PASSED,
)

PROFILE_FAKE = "fake"
PROFILE_NONE = "none"
PROFILE_SHELL = "shell"


class PatchBenchmarkError(BenchmarkError):
    """A patch benchmark case could not be run."""


# =============================================================
# PROPOSALS
# =============================================================

def proposal_from_dict(data):
    """Rebuild a PatchProposal from its serialized form."""

    if not isinstance(data, dict):
        raise PatchBenchmarkError("proposal must be a JSON object")

    files = []

    for entry in data.get("files") or []:
        files.append(
            PatchFile(
                path=entry["path"],
                language=entry.get("language") or "unknown",
                hunks=tuple(
                    PatchHunk(
                        start_line=hunk["start_line"],
                        end_line=hunk["end_line"],
                        old_text=hunk["old_text"],
                        new_text=hunk["new_text"],
                    )
                    for hunk in entry.get("hunks") or []
                ),
            )
        )

    return PatchProposal(
        status=data.get("status") or "invalid",
        summary=data.get("summary") or "",
        reasoning=data.get("reasoning") or "",
        files=files,
        confidence=data.get("confidence"),
        warnings=list(data.get("warnings") or []),
        errors=list(data.get("errors") or []),
    )


def canned_proposal_path(case_path):
    """Canned proposal for a case, by convention `<stem>_good.json`."""

    if not case_path:
        return None

    return CANNED_PROPOSALS / f"{Path(case_path).stem}_good.json"


def load_canned_proposal(case_path):
    path = canned_proposal_path(case_path)

    if path is None or not path.exists():
        raise PatchBenchmarkError(
            f"no canned proposal for {case_path} (expected {path})"
        )

    return proposal_from_dict(json.loads(path.read_text()))


def obtain_proposal(source, prepared, package, generator=None):
    """
    Produce the proposal under test.

    A generator that raises is reported as a generation failure rather
    than allowed to abort the run: an unavailable model is a fact about
    the run, not a score of zero.

    `generator` is required for the generated source. Defaulting to a
    bare PatchGeneratorService() would silently construct one with no
    model and report "LLM service is not configured" as though it were
    a property of the patch.
    """

    if source == SOURCE_CANNED:
        return load_canned_proposal(prepared.get("case_path")), None

    if generator is None:
        raise PatchBenchmarkError(
            "generated proposals need a PatchGeneratorService "
            "with a model attached"
        )

    try:
        return generator.generate(
            prepared["issue"],
            prepared["diagnosis"],
            package,
        ), None
    except Exception as error:
        return None, str(error)


def is_usable(proposal):
    """A proposal a validator could meaningfully attempt."""

    return bool(
        proposal
        and proposal.status == STATUS_OK
        and proposal.files
    )


# =============================================================
# SNAPSHOT OVERRIDE
# =============================================================

def snapshot_for_case(case, snapshot_path=None):
    """
    Load the snapshot for one run.

    `snapshot_path` overrides `case["snapshot"]` for this invocation
    only. The case dict is not modified.
    """

    if snapshot_path is None:
        return load_snapshot(case)

    return load_snapshot({"snapshot": str(snapshot_path)})


def snapshot_from_args(args):
    """
    Optional CLI override. Refused with --cases: one file cannot
    stand in for every case in a directory.
    """

    path = getattr(args, "snapshot", None)

    if not path:
        return None

    if getattr(args, "cases", None):
        raise PatchBenchmarkError(
            "--snapshot can only be used with --case, not --cases"
        )

    try:
        return snapshot_for_case({"snapshot": path}, snapshot_path=path)
    except BenchmarkError as error:
        raise PatchBenchmarkError(str(error)) from error


# =============================================================
# VALIDATION PROFILES
# =============================================================

def build_validation(profile, files=None, timeout_seconds=120.0):
    """
    Commands, runner and honesty label for a profile.

    The Flutter profile inspects `files` and only emits toolchain
    argv when the tree is runnable. The label travels into the report
    because "PASS" from the fake runner and "PASS" from a real
    toolchain are not the same claim.
    """

    if profile == PROFILE_NONE:
        return ValidationConfig(commands=[]), None, "no commands"

    inspection = FlutterValidationProfile().inspect(files)

    if not inspection.runnable:
        reason = inspection.reason or "snapshot is not a Flutter project"
        return (
            ValidationConfig(commands=[]),
            None,
            f"not runnable: {reason}",
        )

    config = ValidationConfig(
        commands=list(inspection.commands),
        timeout_seconds=timeout_seconds,
    )

    if profile == PROFILE_SHELL:
        return config, ShellValidationCommandRunner(), "real toolchain"

    return config, FakeValidationCommandRunner(), "fake runner"


# =============================================================
# SCORING
# =============================================================

def predicted_files(proposal):
    if not proposal:
        return []

    return sorted({file.path for file in proposal.files})


def score_files(expected, predicted):
    """
    Overlap between the historical fix and the generated patch.

    Diagnostics, deliberately not the verdict. A patch touching a file
    the historical fix did not is not thereby wrong — it may be a
    different, equally valid repair.
    """

    expected_set = set(expected or ())
    predicted_set = set(predicted or ())

    hits = expected_set & predicted_set

    recall = (
        len(hits) / len(expected_set) if expected_set else 1.0
    )
    precision = (
        len(hits) / len(predicted_set) if predicted_set else 0.0
    )

    return {
        "expected_files": sorted(expected_set),
        "predicted_files": sorted(predicted_set),
        "matched_files": sorted(hits),
        "unexpected_files": sorted(predicted_set - expected_set),
        "missing_files": sorted(expected_set - predicted_set),
        "file_recall": recall,
        "file_precision": precision,
        "expected_file_touched": expected_set.issubset(predicted_set),
    }


def classify_stage(proposal, validation, generation_error=None):
    """How far the case got, as one of STAGES."""

    if generation_error or not is_usable(proposal):
        if proposal is not None and proposal.status == "invalid":
            return STAGE_PROPOSAL_INVALID
        return STAGE_GENERATION_FAILURE

    if validation is None:
        return STAGE_GENERATION_FAILURE

    return {
        STATUS_PROPOSAL_INVALID: STAGE_PROPOSAL_INVALID,
        STATUS_APPLY_FAILED: STAGE_APPLY_FAILURE,
        STATUS_VALIDATION_FAILED: STAGE_VALIDATION_FAILURE,
        STATUS_PASSED: STAGE_PASSED,
    }.get(validation.status, STAGE_VALIDATION_FAILURE)


# =============================================================
# RUN
# =============================================================

def evaluate_prepared(
    prepared,
    source=SOURCE_CANNED,
    profile=PROFILE_FAKE,
    generator=None,
    validator=None,
    budget=None,
):
    """Build context, obtain a proposal, apply it, and score."""

    case = prepared["case"]
    files = prepared["files"]

    package = build_context_package(
        prepared["snapshot"],
        case,
        prepared["analysis"],
        prepared["diagnosis"],
        files,
        budget=budget,
    )

    proposal, generation_error = obtain_proposal(
        source,
        prepared,
        package,
        generator=generator,
    )

    config, runner, profile_label = build_validation(
        profile,
        files=files,
    )

    validation = None

    if is_usable(proposal):
        service = validator or PatchValidatorService(
            command_runner=runner,
        )
        validation = service.validate(proposal, files, config)

    stage = classify_stage(proposal, validation, generation_error)

    scores = score_files(
        prepared["ground_truth"]["affected_files"],
        predicted_files(proposal),
    )

    errors = list(proposal.errors) if proposal else []
    warnings = list(proposal.warnings) if proposal else []

    if generation_error:
        errors.append(generation_error)

    if validation:
        errors.extend(validation.errors)
        warnings.extend(validation.warnings)

    return {
        "case": prepared.get("case_path"),
        "issue": {
            "number": case["issue_number"],
            "title": prepared["issue"]["title"],
        },
        "proposal_source": source,
        "validation_profile": profile,
        "validation_profile_label": profile_label,
        "patch_generated": is_usable(proposal),
        "patch_status": proposal.status if proposal else None,
        "patch_summary": proposal.summary if proposal else None,
        "patch_applied": bool(validation and validation.applied),
        "validation_passed": bool(
            validation and validation.validation_passed
        ),
        "validation_status": validation.status if validation else None,
        "stage": stage,
        "metrics": scores,
        "commands": [
            {
                "name": item.name,
                "argv": list(item.argv),
                "exit_code": item.exit_code,
                "timed_out": item.timed_out,
            }
            for item in (validation.commands if validation else [])
        ],
        "file_results": [
            {
                "path": item.path,
                "applied": item.applied,
                "hunks_applied": item.hunks_applied,
                "error": item.error,
            }
            for item in (validation.files if validation else [])
        ],
        "changed_lines": prepared["changed_lines"],
        "errors": errors,
        "warnings": warnings,
    }


def run_case(
    case,
    github,
    llm,
    snapshot=None,
    snapshot_path=None,
    source=SOURCE_CANNED,
    profile=PROFILE_FAKE,
    generator=None,
    validator=None,
    budget=None,
    extract_signals=False,
):
    if snapshot is None:
        snapshot = snapshot_for_case(case, snapshot_path)

    prepared = prepare_case(
        case,
        github=github,
        llm=llm,
        snapshot=snapshot,
        extract_signals=extract_signals,
    )

    if source == SOURCE_GENERATED and generator is None:
        generator = PatchGeneratorService(llm_service=llm)

    result = evaluate_prepared(
        prepared,
        source=source,
        profile=profile,
        generator=generator,
        validator=validator,
        budget=budget,
    )

    ground_truth = prepared["ground_truth"]

    result.update({
        "repository": ground_truth["repository"],
        "fix_commit": ground_truth["fix_commit"],
        "parent_commit": ground_truth["parent_commit"],
        "signals_pinned": prepared["signals_pinned"],
    })

    return result


def run_all(paths, github, llm, **kwargs):
    """
    Run every case, keeping going after a failure.

    One unreachable case must not discard the others; it is recorded
    as a failure and excluded from the means.
    """

    results = []

    for path in paths:
        try:
            results.append(
                run_case(load_case(path), github=github, llm=llm, **kwargs)
            )
        except Exception as error:
            results.append({
                "case": str(path),
                "failed": True,
                "error": str(error),
            })

    return results


# =============================================================
# REPORT
# =============================================================

def _yes(value):
    return "YES" if value else "NO"


def report(result):
    metrics = result["metrics"]

    print(f"\nCASE   {result['case']}")
    print(
        f"ISSUE  #{result['issue']['number']}  "
        f"{result['issue']['title']}"
    )
    print(
        f"SOURCE {result['proposal_source']}   "
        f"validation: {result['validation_profile']} "
        f"({result['validation_profile_label']})"
    )

    print(f"\n  generated       : {_yes(result['patch_generated'])}")
    print(f"  status          : {result['patch_status']}")

    if result.get("patch_summary"):
        print(f"  summary         : {result['patch_summary'][:70]}")

    print(f"  applied         : {_yes(result['patch_applied'])}")
    print(
        f"  validation      : "
        f"{'PASS' if result['validation_passed'] else 'FAIL'}"
        f"   ({result['validation_status']})"
    )
    print(f"  stage           : {result['stage']}")

    print(f"\n  expected files  : {metrics['expected_files']}")
    print(f"  patched files   : {metrics['predicted_files']}")

    if metrics["missing_files"]:
        print(f"  not patched     : {metrics['missing_files']}")

    if metrics["unexpected_files"]:
        print(
            f"  beyond the fix  : {metrics['unexpected_files']}  "
            f"(not necessarily wrong)"
        )

    print(f"  file recall     : {metrics['file_recall']:.2f}")
    print(f"  file precision  : {metrics['file_precision']:.2f}")

    for item in result["file_results"]:
        state = "applied" if item["applied"] else "FAILED"
        detail = f"  {item['error']}" if item["error"] else ""
        print(
            f"    {state:<8} {item['path']} "
            f"({item['hunks_applied']} hunks){detail}"
        )

    for command in result["commands"]:
        outcome = (
            "timeout"
            if command["timed_out"]
            else f"exit {command['exit_code']}"
        )
        print(
            f"    {command['name']:<8} "
            f"{' '.join(command['argv'])}  ->  {outcome}"
        )

    for error in result["errors"]:
        print(f"    error: {error}")

    for warning in result["warnings"]:
        print(f"    warning: {warning}")


def summarize(results):
    scored = [item for item in results if not item.get("failed")]

    def mean(values):
        return sum(values) / len(values) if values else 0.0

    stages = {stage: 0 for stage in STAGES}

    for item in scored:
        stages[item["stage"]] = stages.get(item["stage"], 0) + 1

    return {
        "cases": len(results),
        "scored": len(scored),
        "failed": len(results) - len(scored),
        "generated": sum(
            1 for item in scored if item["patch_generated"]
        ),
        "applied": sum(1 for item in scored if item["patch_applied"]),
        "validated": sum(
            1 for item in scored if item["validation_passed"]
        ),
        "file_recall": mean(
            [item["metrics"]["file_recall"] for item in scored]
        ),
        "file_precision": mean(
            [item["metrics"]["file_precision"] for item in scored]
        ),
        "stages": stages,
    }


def report_rollup(results, aggregate):
    header = (
        f"{'CASE':<8} {'GENERATED':>10} {'APPLIED':>9} "
        f"{'VALIDATED':>11} {'RECALL':>8} {'PRECISION':>10}"
    )

    print("\nPATCH REPAIR BENCHMARK")
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    for result in results:
        if result.get("failed"):
            print(
                f"{Path(result['case']).stem[:8]:<8} "
                f"{'FAILED':>10}   {result['error'][:44]}"
            )
            continue

        metrics = result["metrics"]

        print(
            f"{'#' + str(result['issue']['number']):<8} "
            f"{_yes(result['patch_generated']):>10} "
            f"{_yes(result['patch_applied']):>9} "
            f"{('PASS' if result['validation_passed'] else 'FAIL'):>11} "
            f"{metrics['file_recall']:>8.2f} "
            f"{metrics['file_precision']:>10.2f}"
        )

    print("-" * len(header))

    scored = aggregate["scored"] or 1

    print(
        f"generation success : {aggregate['generated']}/"
        f"{aggregate['scored']}"
    )
    print(
        f"apply success      : {aggregate['applied']}/"
        f"{aggregate['scored']}"
    )
    print(
        f"validation success : {aggregate['validated']}/"
        f"{aggregate['scored']}"
    )
    print(
        f"mean file recall   : {aggregate['file_recall']:.2f}"
        f"   precision {aggregate['file_precision']:.2f}"
    )

    print("\nfailure stages")
    for stage in STAGES:
        count = aggregate["stages"].get(stage, 0)
        if count:
            print(f"  {stage:<20} {count}")

    if aggregate["failed"]:
        print(
            f"\ncases not scored   : {aggregate['failed']} "
            f"(excluded from every number above)"
        )


# =============================================================
# ENTRY POINT
# =============================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--case", help="run a single case file")
    target.add_argument(
        "--cases",
        metavar="DIR",
        help="run every *.json case in this directory",
    )
    parser.add_argument(
        "--proposals",
        choices=(SOURCE_CANNED, SOURCE_GENERATED),
        default=SOURCE_CANNED,
        help="canned known-good proposals, or real generator output",
    )
    parser.add_argument(
        "--validation",
        choices=(PROFILE_FAKE, PROFILE_NONE, PROFILE_SHELL),
        default=PROFILE_FAKE,
        help="how validation commands are executed",
    )
    parser.add_argument(
        "--extract-signals",
        action="store_true",
        help="ignore pinned signals and run the real extractor",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print structured JSON",
    )
    parser.add_argument(
        "--snapshot",
        metavar="PATH",
        help=(
            "override the case's snapshot file for this run only. "
            "Does not rewrite the case JSON. Only valid with --case."
        ),
    )

    args = parser.parse_args()

    load_dotenv(BACKEND_ENV)

    if not os.getenv("GITHUB_TOKEN"):
        raise PatchBenchmarkError(
            f"GITHUB_TOKEN is not set (looked in {BACKEND_ENV})"
        )

    github = GithubService(os.getenv("GITHUB_TOKEN"))
    llm = LLMService()

    snapshot = snapshot_from_args(args)

    options = {
        "source": args.proposals,
        "profile": args.validation,
        "extract_signals": args.extract_signals,
    }

    if args.cases:
        results = run_all(
            discover_cases(args.cases),
            github=github,
            llm=llm,
            **options,
        )
        aggregate = summarize(results)

        if args.json:
            print(
                json.dumps(
                    {"results": results, "aggregate": aggregate},
                    indent=2,
                    default=str,
                )
            )
            return

        for result in results:
            if not result.get("failed"):
                report(result)

        report_rollup(results, aggregate)
        return

    result = run_case(
        load_case(args.case),
        github=github,
        llm=llm,
        snapshot=snapshot,
        **options,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        report(result)


if __name__ == "__main__":
    try:
        main()
    except PatchBenchmarkError as error:
        print(f"patch benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1)
