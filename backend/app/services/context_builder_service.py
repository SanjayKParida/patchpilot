from dataclasses import dataclass

from app.code_intelligence.types import (
    TIER_CALLER,
    TIER_CONTRACT,
    TIER_DEFECT,
    TIER_DEPENDENCY,
    TIER_SECONDARY,
    TIER_SUPPORTING,
    TIER_TEST,
    BudgetUsage,
    ContextCandidate,
    ContextPackage,
    ContextSlice,
    FileRollup,
    OmittedEntry,
    Span,
)
from app.services.context_budget import ContextBudget

# Relationships that express a contract the defect must keep
# satisfying. Changing a signature without seeing the abstract class
# it overrides produces a patch that does not compile.
CONTRACT_RELATIONSHIPS = ("implements", "extends", "mixes_in")


class ContextBuilderService:
    """
    Selects the code a patch generator needs, and nothing else.

    Language-agnostic by construction. It knows about tiers, priority,
    deduplication and budgets; it knows nothing about Dart, Python or
    TypeScript. Anything that requires reading code is asked of a
    CodeIntelligence adapter, and file-level graph traversal is asked
    of RepositoryGraph, which is already language-free.

    If a test of this class needs a real language, the boundary has
    leaked. The suite exercises it against a fake adapter over invented
    files in no language at all, and that is deliberate.

    This class performs no retrieval and calls no model. Which files
    are relevant was decided upstream by ranking, which has a
    benchmark behind it; re-deciding it here would discard that.
    """

    # How far to follow dependency edges out of the defect site. One
    # hop is what a patch usually needs: the types the defect uses.
    # Two hops pulls in most of a small repository.
    DEPENDENCY_DEPTH = 1

    def __init__(self, code_intelligence, budget=None):
        self.code = code_intelligence
        self.budget = budget or ContextBudget()

    # =========================================================
    # PUBLIC API
    # =========================================================

    def plan(
        self,
        diagnosis=None,
        ranked=None,
        direct_evidence=None,
        graph=None,
        files=None,
        index=None,
    ):
        """
        Ordered, deduplicated candidates — what to include, not yet
        how much of it.

        Returns candidates in tier order. Because eviction is reverse
        tier order, this list can be truncated anywhere and remains
        the best context available at that size.
        """

        ranked = list(ranked or [])
        diagnosis = diagnosis or {}

        if index is None and files:
            index = self.code.build_index(files)

        collected = []
        seen = set()
        claimed_paths = set()

        def admit(candidate, file_level):
            """
            Add a candidate unless an earlier, higher-priority tier
            already covers it.

            File-level candidates collapse against any path already
            present: once a file is in for a strong reason, adding it
            again for a weaker one says nothing new.
            """

            if candidate.key in seen:
                return False

            if file_level and candidate.path in claimed_paths:
                return False

            # Tests belong to their own tier and nowhere else.
            #
            # A test importing the defect otherwise arrives as a
            # CALLER before the test tier is reached, which both
            # over-prioritises it and lets it escape the separate cap
            # the test tier exists to impose.
            if (
                candidate.tier != TIER_TEST
                and self.code.is_test_file(candidate.path)
            ):
                return False

            seen.add(candidate.key)
            claimed_paths.add(candidate.path)
            collected.append(candidate)
            return True

        # -----------------------------------------------------
        # T0 — the defect site
        # -----------------------------------------------------

        defect_paths = []

        for location in diagnosis.get("root_cause_locations") or []:

            candidate = ContextCandidate(
                path=location["path"],
                tier=TIER_DEFECT,
                reason=(
                    f"declares {location['symbol']}, named as the "
                    f"defect site"
                ),
                symbol=location["symbol"],
                line=location.get("line"),
            )

            if admit(candidate, file_level=False):
                defect_paths.append(location["path"])

        if not defect_paths:
            # The model named no symbol, or named one that could not
            # be resolved. Fall back to whole files, widest first:
            # what the diagnosis cited, then what ranking found.
            fallback = self._fallback_defect_path(diagnosis, ranked)

            if fallback:
                admit(
                    ContextCandidate(
                        path=fallback,
                        tier=TIER_DEFECT,
                        reason=(
                            "no defect symbol resolved; included as "
                            "the most likely file"
                        ),
                    ),
                    file_level=True,
                )
                defect_paths.append(fallback)

        # -----------------------------------------------------
        # T1 — supporting declarations
        # -----------------------------------------------------

        for location in diagnosis.get("locations") or []:

            admit(
                ContextCandidate(
                    path=location["path"],
                    tier=TIER_SUPPORTING,
                    reason=(
                        f"declares {location['symbol']}, referenced "
                        f"by the diagnosis"
                    ),
                    symbol=location["symbol"],
                    line=location.get("line"),
                ),
                file_level=False,
            )

        # -----------------------------------------------------
        # T2 — what the defect depends on
        # -----------------------------------------------------

        if graph is not None:

            for path in defect_paths:

                for relationship in graph.get_relationships(path):

                    if relationship["relationship"] != "imports":
                        continue

                    admit(
                        ContextCandidate(
                            path=relationship["target"],
                            tier=TIER_DEPENDENCY,
                            reason=f"imported by {self._name(path)}",
                        ),
                        file_level=True,
                    )

        # -----------------------------------------------------
        # T3 — what depends on the defect
        # -----------------------------------------------------
        #
        # Symbol references first, then file-level importers. The two
        # are not equivalent: a file that branches on a state the
        # defect declares is far stronger evidence than a file that
        # merely imports the file declaring it. Ranking learned this
        # the hard way — a dependency-injection container imports
        # everything.
        # -----------------------------------------------------

        for candidate in list(collected):

            if candidate.tier != TIER_DEFECT or not candidate.symbol:
                continue

            for reference in self.code.references_to(
                candidate.symbol,
                index,
            ):

                admit(
                    ContextCandidate(
                        path=reference.path,
                        tier=TIER_CALLER,
                        reason=(
                            f"uses {reference.symbol} "
                            f"({reference.kind})"
                        ),
                    ),
                    file_level=True,
                )

        if graph is not None:

            for path in defect_paths:

                for importer in graph.get_importers(path):

                    admit(
                        ContextCandidate(
                            path=importer,
                            tier=TIER_CALLER,
                            reason=f"imports {self._name(path)}",
                        ),
                        file_level=True,
                    )

        # -----------------------------------------------------
        # T4 — contracts the defect must keep satisfying
        # -----------------------------------------------------

        if graph is not None:

            for path in defect_paths:

                for relationship in graph.get_relationships(path):

                    if relationship["relationship"] not in (
                        CONTRACT_RELATIONSHIPS
                    ):
                        continue

                    admit(
                        ContextCandidate(
                            path=relationship["target"],
                            tier=TIER_CONTRACT,
                            reason=(
                                f"{self._name(path)} "
                                f"{relationship['relationship']} it"
                            ),
                        ),
                        file_level=True,
                    )

                for relationship in graph.get_reverse_relationships(
                    path
                ):

                    if relationship["relationship"] not in (
                        CONTRACT_RELATIONSHIPS
                    ):
                        continue

                    admit(
                        ContextCandidate(
                            path=relationship["source"],
                            tier=TIER_CONTRACT,
                            reason=(
                                f"{relationship['relationship']} "
                                f"{self._name(path)}"
                            ),
                        ),
                        file_level=True,
                    )

        # -----------------------------------------------------
        # T5 — tests covering the code being changed
        # -----------------------------------------------------

        for path in self._test_paths(ranked, files):

            if not self._touches(path, claimed_paths, graph):
                continue

            admit(
                ContextCandidate(
                    path=path,
                    tier=TIER_TEST,
                    reason="test covering the changed code",
                ),
                file_level=True,
            )

        # -----------------------------------------------------
        # T6 — everything else ranking surfaced
        # -----------------------------------------------------

        for entry in ranked:

            admit(
                ContextCandidate(
                    path=entry["path"],
                    tier=TIER_SECONDARY,
                    reason=f"ranked #{entry.get('rank', '?')} by retrieval",
                ),
                file_level=True,
            )

        collected.sort(key=lambda item: (item.tier, item.line or 0, item.path))

        return collected

    def build(
        self,
        diagnosis=None,
        ranked=None,
        graph=None,
        files=None,
        index=None,
        issue=None,
        budget=None,
        direct_evidence=None,
    ):
        """
        Slice, merge, and budget the plan into a ContextPackage.

        `direct_evidence` is accepted so callers can pass the ranking
        bundle through unchanged; this layer does not re-rank.
        """

        del direct_evidence

        budget = budget or self.budget
        files = files or []
        diagnosis = diagnosis or {}
        by_path = {
            file["path"]: file.get("content") or ""
            for file in files
            if file.get("path")
        }

        if index is None and files:
            index = self.code.build_index(files)

        candidates = self.plan(
            diagnosis=diagnosis,
            ranked=ranked,
            graph=graph,
            files=files,
            index=index,
        )

        omitted = []
        seen_omitted = set()
        warnings = []

        def record_omitted(path, reason):
            if path in seen_omitted:
                return
            seen_omitted.add(path)
            omitted.append(OmittedEntry(path=path, reason=reason))

        drafts = []
        resolved_paths = set()

        for candidate in candidates:
            if candidate.path not in by_path:
                record_omitted(candidate.path, "unresolved")
                continue

            resolved_paths.add(candidate.path)
            drafts.append(
                self._slice_candidate(
                    candidate,
                    by_path[candidate.path],
                    index,
                    budget,
                )
            )

        drafts = self._add_headers(drafts, by_path, index)
        drafts = self._merge_and_collapse(drafts, by_path, budget)
        drafts, over_budget, budget_warning = self._apply_budget(
            drafts,
            by_path,
            budget,
        )

        kept_paths = {draft.path for draft in drafts}

        for path in sorted(resolved_paths):
            if path not in kept_paths:
                record_omitted(path, "budget_exhausted")

        if any(
            candidate.tier == TIER_DEFECT and not candidate.symbol
            for candidate in candidates
        ):
            warnings.append(
                "no defect symbol resolved; included as the most likely file"
            )

        if budget_warning:
            warnings.append(budget_warning)

        drafts.sort(key=lambda item: (item.tier, item.path, item.start_line))

        slices = [
            self._materialize(draft, by_path[draft.path])
            for draft in drafts
        ]

        rollup = self._file_rollups(slices, by_path)
        chars = sum(len(item.content) for item in slices)
        tokens = (
            chars // budget.chars_per_token
            if budget.chars_per_token
            else 0
        )

        root_cause = None
        locations = diagnosis.get("root_cause_locations") or []
        if locations:
            location = locations[0]
            root_cause = {
                "symbol": location.get("symbol"),
                "path": location.get("path"),
                "line": location.get("line"),
                "kind": location.get("kind"),
            }

        language, adapter_name = self._package_identity(slices)

        return ContextPackage(
            issue=issue,
            diagnosis=diagnosis,
            root_cause=root_cause,
            slices=slices,
            files=rollup,
            omitted=omitted,
            warnings=warnings,
            budget=BudgetUsage(
                max_files=budget.max_files,
                files_used=len({item.path for item in slices}),
                max_lines_total=budget.max_lines_total,
                lines_used=sum(item.line_count for item in slices),
                estimated_tokens=tokens,
                over_budget=over_budget,
            ),
            language=language,
            adapter=adapter_name,
        )

    # =========================================================
    # INTERNALS
    # =========================================================

    @staticmethod
    def _fallback_defect_path(diagnosis, ranked):
        for path in diagnosis.get("relevant_files") or []:
            return path

        for entry in ranked:
            return entry.get("path")

        return None

    def _test_paths(self, ranked, files):
        paths = [entry["path"] for entry in ranked]

        for file in files or []:
            if file.get("path") not in paths:
                paths.append(file["path"])

        return [
            path
            for path in paths
            if self.code.is_test_file(path)
        ]

    @staticmethod
    def _touches(test_path, claimed_paths, graph):
        """
        Whether a test file reaches any code already being included.

        Without this every test in the repository qualifies, which is
        how a context package fills up with tests for unrelated
        features.
        """

        if graph is None:
            return False

        return any(
            relationship["target"] in claimed_paths
            for relationship in graph.get_relationships(test_path)
        )

    @staticmethod
    def _name(path):
        return path.split("/")[-1]

    def _adapter_for(self, path):
        """
        The adapter that owns this path.

        A registry exposes `for_path`; a single adapter (including the
        test fake) is used as-is. The core never branches on language.
        """

        lookup = getattr(self.code, "for_path", None)
        if callable(lookup):
            return lookup(path)
        return self.code

    def _package_identity(self, slices):
        languages = list(
            dict.fromkeys(item.language for item in slices if item.language)
        )
        adapters = list(
            dict.fromkeys(item.adapter for item in slices if item.adapter)
        )

        if not languages:
            return self.code.name, type(self.code).__name__

        language = languages[0] if len(languages) == 1 else "mixed"
        adapter = adapters[0] if len(adapters) == 1 else "mixed"
        return language, adapter

    def _slice_candidate(self, candidate, content, index, budget):
        lines = _split_lines(content)
        n = len(lines)
        symbols = [candidate.symbol] if candidate.symbol else []

        if n == 0:
            return _Draft(
                path=candidate.path,
                start_line=1,
                end_line=0,
                tier=candidate.tier,
                reason=candidate.reason,
                symbols=symbols,
                truncated=False,
            )

        truncated = False

        if candidate.line:
            span = self.code.enclosing_span(
                candidate.path,
                candidate.line,
                index,
            )

            if span is not None:
                start = span.start_line
                end = span.end_line
            else:
                start = candidate.line - budget.fallback_before
                end = candidate.line + budget.fallback_after
                truncated = True

            start -= budget.pad_lines
            end += budget.pad_lines
        else:
            start = 1
            end = n

        start, end = _clamp(start, end, n)

        return _Draft(
            path=candidate.path,
            start_line=start,
            end_line=end,
            tier=candidate.tier,
            reason=candidate.reason,
            symbols=symbols,
            truncated=truncated,
        )

    def _add_headers(self, drafts, by_path, index):
        grouped = {}
        for draft in drafts:
            grouped.setdefault(draft.path, []).append(draft)

        extra = []

        for path, group in grouped.items():
            content = by_path[path]
            header_end = self.code.header_end_line(path, content, index)

            if not header_end:
                continue

            n = len(_split_lines(content))
            header_end = min(int(header_end), n) if n else 0

            if header_end < 1:
                continue

            best = min(group, key=lambda item: (item.tier, item.start_line))
            extra.append(
                _Draft(
                    path=path,
                    start_line=1,
                    end_line=header_end,
                    tier=best.tier,
                    reason="file header",
                    symbols=[],
                    truncated=False,
                )
            )

        return drafts + extra

    def _merge_and_collapse(self, drafts, by_path, budget):
        grouped = {}
        for draft in drafts:
            grouped.setdefault(draft.path, []).append(draft)

        merged = []

        for path in sorted(grouped):
            file_drafts = self._merge_file(grouped[path], budget.merge_gap)
            file_drafts = self._collapse_file(
                file_drafts,
                by_path[path],
                budget.whole_file_fraction,
            )
            merged.extend(file_drafts)

        merged.sort(key=lambda item: (item.tier, item.path, item.start_line))
        return merged

    @staticmethod
    def _merge_file(drafts, gap):
        drafts = sorted(
            drafts,
            key=lambda item: (item.start_line, item.end_line, item.tier),
        )
        merged = []

        for draft in drafts:
            if not merged:
                merged.append(draft)
                continue

            previous = merged[-1]
            left = Span(
                path=previous.path,
                start_line=previous.start_line,
                end_line=previous.end_line,
                kind="slice",
            )
            right = Span(
                path=draft.path,
                start_line=draft.start_line,
                end_line=draft.end_line,
                kind="slice",
            )

            if not left.overlaps(right, gap=gap):
                merged.append(draft)
                continue

            if draft.tier < previous.tier:
                previous.reason = draft.reason
                previous.tier = draft.tier
            elif (
                draft.tier == previous.tier
                and draft.symbols
                and not previous.symbols
            ):
                previous.reason = draft.reason

            previous.start_line = min(previous.start_line, draft.start_line)
            previous.end_line = max(previous.end_line, draft.end_line)
            previous.truncated = previous.truncated or draft.truncated

            for symbol in draft.symbols:
                if symbol and symbol not in previous.symbols:
                    previous.symbols.append(symbol)

        return merged

    @staticmethod
    def _collapse_file(drafts, content, fraction):
        lines = _split_lines(content)
        n = len(lines)

        if n == 0 or not drafts:
            return drafts

        included = sum(item.line_count for item in drafts)

        if included / n < fraction:
            return drafts

        best = min(drafts, key=lambda item: (item.tier, item.start_line))
        symbols = []
        for draft in drafts:
            for symbol in draft.symbols:
                if symbol and symbol not in symbols:
                    symbols.append(symbol)

        return [
            _Draft(
                path=best.path,
                start_line=1,
                end_line=n,
                tier=best.tier,
                reason=best.reason,
                symbols=symbols,
                truncated=False,
            )
        ]

    def _apply_budget(self, drafts, by_path, budget):
        drafts = list(drafts)
        over_budget = False
        warning = None

        drafts = self._cap_tests(drafts, budget)
        drafts = self._cap_per_file(drafts, budget)

        drafts.sort(key=lambda item: (item.tier, item.path, item.start_line))

        while self._exceeds(drafts, by_path, budget):
            index = None
            for i in range(len(drafts) - 1, -1, -1):
                if drafts[i].tier != TIER_DEFECT:
                    index = i
                    break

            if index is None:
                over_budget = True
                warning = "defect site exceeds budget; included anyway"
                break

            drafts.pop(index)

        t0_lines_by_path = {}
        for draft in drafts:
            if draft.tier != TIER_DEFECT:
                continue
            t0_lines_by_path[draft.path] = (
                t0_lines_by_path.get(draft.path, 0) + draft.line_count
            )

        if any(
            count > budget.max_lines_per_file
            for count in t0_lines_by_path.values()
        ):
            over_budget = True
            warning = "defect site exceeds budget; included anyway"

        return drafts, over_budget, warning

    def _cap_tests(self, drafts, budget):
        test_paths = []
        for draft in drafts:
            if (
                self.code.is_test_file(draft.path)
                and draft.path not in test_paths
            ):
                test_paths.append(draft.path)

        if len(test_paths) <= budget.max_tests:
            return drafts

        keep = set(test_paths[: budget.max_tests])
        return [
            draft
            for draft in drafts
            if not self.code.is_test_file(draft.path) or draft.path in keep
        ]

    @staticmethod
    def _cap_per_file(drafts, budget):
        grouped = {}
        for draft in drafts:
            grouped.setdefault(draft.path, []).append(draft)

        kept = []

        for path in sorted(grouped):
            file_drafts = sorted(
                grouped[path],
                key=lambda item: (item.tier, item.start_line),
            )
            t0 = [item for item in file_drafts if item.tier == TIER_DEFECT]
            others = [
                item for item in file_drafts if item.tier != TIER_DEFECT
            ]

            t0_lines = sum(item.line_count for item in t0)
            kept.extend(t0)

            if t0_lines > budget.max_lines_per_file:
                continue

            used = t0_lines
            for draft in others:
                if used + draft.line_count <= budget.max_lines_per_file:
                    kept.append(draft)
                    used += draft.line_count

        return kept

    def _exceeds(self, drafts, by_path, budget):
        if len({item.path for item in drafts}) > budget.max_files:
            return True

        lines = sum(item.line_count for item in drafts)

        if budget.max_tokens is None:
            return lines > budget.max_lines_total

        chars = 0
        for draft in drafts:
            content = _extract(
                _split_lines(by_path.get(draft.path, "")),
                draft.start_line,
                draft.end_line,
            )
            chars += len(content)

        tokens = chars // budget.chars_per_token if budget.chars_per_token else 0
        return tokens > budget.max_tokens

    def _materialize(self, draft, content):
        lines = _split_lines(content)
        intelligence = self._adapter_for(draft.path)
        return ContextSlice(
            path=draft.path,
            start_line=draft.start_line,
            end_line=draft.end_line,
            tier=draft.tier,
            reason=draft.reason,
            symbols=tuple(symbol for symbol in draft.symbols if symbol),
            content=_extract(lines, draft.start_line, draft.end_line),
            truncated=draft.truncated,
            language=intelligence.name,
            adapter=type(intelligence).__name__,
        )

    @staticmethod
    def _file_rollups(slices, by_path):
        order = []
        for item in slices:
            if item.path not in order:
                order.append(item.path)

        rollups = []
        for path in order:
            total = len(_split_lines(by_path.get(path, "")))
            included = sum(
                item.line_count for item in slices if item.path == path
            )
            rollups.append(
                FileRollup(
                    path=path,
                    total_lines=total,
                    included_lines=included,
                    complete=total > 0 and included == total,
                )
            )

        return rollups


@dataclass
class _Draft:
    path: str
    start_line: int
    end_line: int
    tier: int
    reason: str
    symbols: list
    truncated: bool

    @property
    def line_count(self):
        if self.end_line < self.start_line:
            return 0
        return self.end_line - self.start_line + 1


def _split_lines(content):
    if not content:
        return []
    return content.splitlines()


def _clamp(start, end, n):
    if n <= 0:
        return 1, 0
    start = max(1, min(start, n))
    end = max(1, min(end, n))
    if end < start:
        end = start
    return start, end


def _extract(lines, start, end):
    if not lines or end < start:
        return ""
    return "\n".join(lines[start - 1 : end])
