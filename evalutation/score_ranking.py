"""
Score the retrieval pipeline against a ground-truth case.

This exists so that calibration is a measurement rather than an
opinion. It changes nothing about how ranking works; it only reports
where the current output disagrees with the expected output.

Usage
-----

    PYTHONPATH=backend python -m evalutation.score_ranking
    PYTHONPATH=backend python -m evalutation.score_ranking --case cars_loading
    PYTHONPATH=backend python -m evalutation.score_ranking --baseline out.json
    PYTHONPATH=backend python -m evalutation.score_ranking --compare out.json
"""

import argparse
import json
from pathlib import Path

from evalutation.pipeline import load_fixture, run_quiet


CASE_DIR = Path(__file__).parent / "cases"

TIER_1_WINDOW = 5

TIER_2_WINDOW = 10


# ============================================================
# LOADING
# ============================================================

def load_case(name):
    path = Path(name)

    if not path.exists():
        path = CASE_DIR / f"{name}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"no case named {name} (looked in {CASE_DIR})"
        )

    return json.loads(path.read_text())


# ============================================================
# SCORING
# ============================================================

def evaluate(case, result):
    ranked = result["ranked"]

    rank_by_path = {
        entry["path"]: entry["rank"]
        for entry in ranked
    }

    def assess(expected, window):
        rows = []

        for position, item in enumerate(expected, start=1):
            path = item["path"]
            actual = rank_by_path.get(path)

            rows.append({
                "path": path,
                "ideal": position,
                "actual": actual,
                "in_window": (
                    actual is not None
                    and actual <= window
                ),
                "why": item["why"],
            })

        return rows

    tier_1 = assess(case["tier_1"], TIER_1_WINDOW)
    tier_2 = assess(case["tier_2"], TIER_2_WINDOW)

    violations = []

    for item in case["must_not_rank_top_5"]:
        actual = rank_by_path.get(item["path"])

        if actual is not None and actual <= TIER_1_WINDOW:
            violations.append({
                "path": item["path"],
                "actual": actual,
                "why": item["why"],
            })

    return {
        "tier_1": tier_1,
        "tier_2": tier_2,
        "violations": violations,
        "metrics": {
            "tier_1_in_top_5": sum(
                1 for row in tier_1 if row["in_window"]
            ),
            "tier_1_total": len(tier_1),
            "tier_2_in_top_10": sum(
                1 for row in tier_2 if row["in_window"]
            ),
            "tier_2_total": len(tier_2),
            "missing_entirely": sum(
                1
                for row in tier_1 + tier_2
                if row["actual"] is None
            ),
            "violations": len(violations),
        },
    }


# ============================================================
# SIGNAL COVERAGE
# ============================================================

def signal_coverage(result):
    """
    How many distinct issue signals each file carries evidence for.

    Breadth across an issue's concepts is a different thing from
    volume on one concept, and the ranking currently cannot tell
    them apart. This table makes the difference visible.
    """

    coverage = {}

    for record in result["direct_evidence"]:
        path = record["file"]["path"]

        coverage.setdefault(path, set()).add(
            record["concept"]
        )

    return coverage


# ============================================================
# REPORTING
# ============================================================

def _fmt_rank(rank):
    return "--" if rank is None else str(rank)


def report(case, result, evaluation):
    ranked = result["ranked"]
    coverage = signal_coverage(result)
    signal_count = len(result["signals"])

    print(f"\nCASE   {case['name']}")
    print(f"ISSUE  {case['issue_title']}")
    print(
        f"SIGNALS  "
        + ", ".join(
            signal["term"] for signal in result["signals"]
        )
    )

    # --------------------------------------------------------
    # Ranked output
    # --------------------------------------------------------

    print(
        f"\n{'='*78}\n"
        f"RANKED OUTPUT (top {TIER_2_WINDOW})\n"
        f"{'='*78}"
    )

    print(
        f"{'#':>3}  {'file':<46} {'total':>7} "
        f"{'sig':>4}  direct  struct   mean confidence"
    )

    for entry in ranked[:TIER_2_WINDOW]:
        path = entry["path"]
        matched = len(coverage.get(path, ()))

        # Confidences accumulate once per matched signal; show the
        # average so channels stay comparable across files.
        divisor = max(entry["signals_matched"], 1)

        print(
            f"{entry['rank']:>3}  "
            f"{path.replace('lib/', ''):<46} "
            f"{entry['total_score']:>7.2f} "
            f"{matched:>2}/{signal_count}  "
            f"{entry['direct_score']:>6.2f}  "
            f"{entry['structural_score']:>6.2f}   "
            f"e={entry['evidence_confidence'] / divisor:.2f} "
            f"c={entry['content_confidence'] / divisor:.2f} "
            f"p={entry['path_confidence'] / divisor:.2f}"
        )

    # --------------------------------------------------------
    # Tiers
    # --------------------------------------------------------

    for tier, rows, window in (
        ("TIER 1", evaluation["tier_1"], TIER_1_WINDOW),
        ("TIER 2", evaluation["tier_2"], TIER_2_WINDOW),
    ):
        print(
            f"\n{'='*78}\n"
            f"{tier} — expected inside top {window}\n"
            f"{'='*78}"
        )

        print(
            f"{'ideal':>5} {'actual':>6}  "
            f"{'file':<46} {'sig':>4}"
        )

        for row in rows:
            mark = " " if row["in_window"] else "!"
            matched = len(coverage.get(row["path"], ()))

            print(
                f"{row['ideal']:>5} "
                f"{_fmt_rank(row['actual']):>6}{mark} "
                f"{row['path'].replace('lib/', ''):<46} "
                f"{matched:>2}/{signal_count}"
            )

    # --------------------------------------------------------
    # Distractors
    # --------------------------------------------------------

    print(
        f"\n{'='*78}\n"
        f"DISTRACTORS — must not appear in top {TIER_1_WINDOW}\n"
        f"{'='*78}"
    )

    if evaluation["violations"]:
        for violation in evaluation["violations"]:
            print(
                f"  FAIL  #{violation['actual']}  "
                f"{violation['path']}"
            )
            print(f"        {violation['why']}")
    else:
        print("  none in top 5")

    for item in case["must_not_rank_top_5"]:
        rank = next(
            (
                entry["rank"]
                for entry in ranked
                if entry["path"] == item["path"]
            ),
            None,
        )

        if rank is not None and rank <= TIER_2_WINDOW:
            print(
                f"  note  #{rank}  {item['path']} "
                f"(inside top {TIER_2_WINDOW})"
            )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    metrics = evaluation["metrics"]

    print(
        f"\n{'='*78}\n"
        f"SUMMARY\n"
        f"{'='*78}"
    )

    print(
        f"  tier 1 in top {TIER_1_WINDOW}   "
        f"{metrics['tier_1_in_top_5']}/{metrics['tier_1_total']}"
    )
    print(
        f"  tier 2 in top {TIER_2_WINDOW}  "
        f"{metrics['tier_2_in_top_10']}/{metrics['tier_2_total']}"
    )
    print(
        f"  never ranked     "
        f"{metrics['missing_entirely']}"
    )
    print(
        f"  distractors in top {TIER_1_WINDOW}  "
        f"{metrics['violations']}"
    )


# ============================================================
# BASELINE COMPARISON
# ============================================================

def to_baseline(result, evaluation):
    return {
        "metrics": evaluation["metrics"],
        "ranked": [
            {
                "rank": entry["rank"],
                "path": entry["path"],
                "total_score": round(entry["total_score"], 4),
            }
            for entry in result["ranked"]
        ],
    }


def compare(previous, result, evaluation):
    print(
        f"\n{'='*78}\n"
        f"COMPARED TO BASELINE\n"
        f"{'='*78}"
    )

    old_metrics = previous["metrics"]
    new_metrics = evaluation["metrics"]

    for key, value in new_metrics.items():
        old = old_metrics.get(key)

        if old == value:
            continue

        print(f"  {key}: {old} -> {value}")

    old_ranks = {
        entry["path"]: entry["rank"]
        for entry in previous["ranked"]
    }

    moved = []

    for entry in result["ranked"]:
        old = old_ranks.get(entry["path"])

        if old is None:
            moved.append((entry["path"], None, entry["rank"]))
        elif old != entry["rank"]:
            moved.append((entry["path"], old, entry["rank"]))

    if not moved:
        print("  no rank changes")
        return

    for path, old, new in sorted(
        moved,
        key=lambda item: item[2],
    ):
        arrow = "new" if old is None else f"{old} -> {new}"
        print(f"  {path.replace('lib/', ''):<46} {arrow}")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="cars_loading")
    parser.add_argument(
        "--baseline",
        help="write the current result to this path",
    )
    parser.add_argument(
        "--compare",
        help="compare the current result against a saved baseline",
    )

    args = parser.parse_args()

    case = load_case(args.case)
    snapshot = load_fixture(case["fixture"])

    # Ranking eval stays independent of the LLM: cases inject their
    # manual signals, and pipeline.py uses IssueSignalService when
    # a case has none.
    result = run_quiet(
        snapshot,
        signals=case.get("signals"),
    )
    evaluation = evaluate(case, result)

    report(case, result, evaluation)

    if args.compare:
        compare(
            json.loads(Path(args.compare).read_text()),
            result,
            evaluation,
        )

    if args.baseline:
        Path(args.baseline).write_text(
            json.dumps(
                to_baseline(result, evaluation),
                indent=2,
            )
        )
        print(f"\nbaseline written to {args.baseline}")


if __name__ == "__main__":
    main()
