"""
Derive benchmark ground truth from a fix commit.

Hand-labelling a benchmark does not scale: the `cars_loading` case
took reading an entire repository. A closed issue with its fix commit
already contains the answer — the files the fix changed are the files
retrieval was supposed to find.

This module turns a fix commit into that answer, for one repository at
a time. It reads GitHub and computes; it does not rank, diagnose, or
snapshot anything.

    fix commit
        -> first parent          (the state the bug lived in)
        -> diff parent..fix      (everything the fix touched)
        -> keep product source   (what retrieval could plausibly find)
        -> affected_files

Filtering is the whole difficulty. A real fix commit also touches
tests, changelogs and generated code, and counting those as ground
truth turns the benchmark into noise. Every exclusion is recorded with
a reason so a disputed case can be inspected rather than argued about.
"""

# Flutter product code lives under lib/. Everything outside it --
# tests, tooling, docs, lockfiles, platform folders, CI config -- is
# excluded by this one rule rather than by a list of patterns that
# would need endless maintenance.
PRODUCT_ROOT = "lib/"

SOURCE_SUFFIX = ".dart"

# Written by build_runner and friends. A fix never lands here; the
# generator input changed instead.
GENERATED_SUFFIXES = (
    ".g.dart",
    ".freezed.dart",
    ".gr.dart",
    ".config.dart",
    ".mocks.dart",
    ".pb.dart",
    ".pbenum.dart",
    ".pbjson.dart",
    ".pbserver.dart",
)

GENERATED_NAMES = (
    "generated_plugin_registrant.dart",
)

# Tests can live under lib/ in some layouts, so the suffix is checked
# independently of the directory rule.
TEST_SUFFIX = "_test.dart"

# Reasons a changed file did not become ground truth.
NOT_PRODUCT = "not_product_source"
GENERATED = "generated"
TEST = "test"
ADDED = "added_by_fix"


class GroundTruthError(RuntimeError):
    """Ground truth could not be derived for a commit."""


# =============================================================
# CLASSIFICATION
# =============================================================

def exclusion_reason(path):
    """
    Why this path is not benchmark ground truth, or None to keep it.
    """

    if not path.endswith(SOURCE_SUFFIX):
        return NOT_PRODUCT

    if not path.startswith(PRODUCT_ROOT):
        return NOT_PRODUCT

    if path.endswith(TEST_SUFFIX):
        return TEST

    if path.endswith(GENERATED_SUFFIXES):
        return GENERATED

    if path.rsplit("/", 1)[-1] in GENERATED_NAMES:
        return GENERATED

    return None


def pre_fix_path(entry):
    """
    Where this file lived BEFORE the fix.

    Ground truth is compared against a pre-fix snapshot, so a renamed
    file has to be reported at its old path — the new one does not
    exist yet in the tree being searched.
    """

    if entry.get("status") == "renamed" and entry.get(
        "previous_filename"
    ):
        return entry["previous_filename"]

    return entry.get("filename")


# =============================================================
# DERIVATION
# =============================================================

def derive_ground_truth(github, owner, repo, fix_commit):
    """
    Ground truth for one fix commit.

    Returns
    -------
    dict
        {
            "repository": "owner/repo",
            "fix_commit": "<sha>",
            "parent_commit": "<sha>",
            "affected_files": [...],   # the answer
            "changed_files": [...],    # everything the fix touched
            "excluded": [{"path", "reason"}]
        }

    `changed_files` and `excluded` exist so the filtering can be
    audited. A benchmark whose ground truth cannot be inspected is a
    benchmark nobody should trust.
    """

    commit = _get_commit(github, owner, repo, fix_commit)

    parents = commit.get("parents") or []

    if not parents:
        raise GroundTruthError(
            f"{fix_commit} has no parent commit, so there is no "
            f"pre-fix state to compare against"
        )

    parent_sha = parents[0]["sha"]

    try:
        comparison = github.compare_commits(
            owner,
            repo,
            parent_sha,
            commit["sha"],
        )
    except Exception as e:
        raise GroundTruthError(
            f"Could not diff {parent_sha}..{commit['sha']} in "
            f"{owner}/{repo}: {e}"
        ) from e

    changed = []
    affected = []
    excluded = []

    for entry in comparison.get("files") or []:

        path = pre_fix_path(entry)

        if not path:
            continue

        changed.append(path)

        # A file the fix CREATED is absent from the pre-fix tree, so
        # no retriever could rank it. Counting it would make the case
        # unwinnable rather than hard.
        if entry.get("status") == "added":
            excluded.append({"path": path, "reason": ADDED})
            continue

        reason = exclusion_reason(path)

        if reason:
            excluded.append({"path": path, "reason": reason})
            continue

        affected.append(path)

    return {
        "repository": f"{owner}/{repo}",
        "fix_commit": commit["sha"],
        "parent_commit": parent_sha,
        "affected_files": sorted(set(affected)),
        "changed_files": sorted(set(changed)),
        "excluded": sorted(
            excluded,
            key=lambda item: item["path"],
        ),
    }


def _get_commit(github, owner, repo, ref):
    try:
        commit = github.get_commit(owner, repo, ref)
    except Exception as e:
        raise GroundTruthError(
            f"Could not resolve {ref} in {owner}/{repo}: {e}"
        ) from e

    if not isinstance(commit, dict) or "sha" not in commit:
        raise GroundTruthError(
            f"{ref} is not a commit in {owner}/{repo}"
        )

    return commit
