# PatchPilot — Agent Context

Use this document as shared project context for any agent working on PatchPilot.
Prefer this over inventing architecture. If this conflicts with code, **trust the code**, then update this file.

Related product notes live in `PATCHPILOT.md`. This file is the **working engineering context**.

---

## 1. What PatchPilot is

PatchPilot is an automated debugging pipeline:

```text
GitHub issue + repository
    → extract signals
    → retrieve relevant code (deterministic, code-aware)
    → understand structural relationships
    → rank the best candidate files
    → give focused context to an LLM
    → diagnose root cause + propose a fix
    → ContextBuilder → PatchGenerator → PatchValidator
    → developer review / local approval
    → (later) GitHub branch / commit / PR
```

### Core principle

| Layer | Responsibility | Nature |
|-------|----------------|--------|
| Search, structure, graph, evidence, ranking | Find *which* files matter and *why* | Deterministic, code-aware |
| LLM | Reason about the *bug* and *solution* | Probabilistic, constrained by evidence |

**Do not** give the LLM the whole repository.
**Do** give: issue + small set of highly relevant files + evidence/relationships explaining why they matter.

### Non-goals (MVP)

- No multi-repo support in MVP
- Agent must not merge PRs itself
- Not a general-purpose coding agent — GitHub-issue-driven only
- Apply/verify loop comes after retrieval + diagnosis are solid

---

## 2. Current maturity

```text
████████████░░░░░░░░  retrieval / ranking MVP
████████░░░░░░░░░░░░  LLM diagnosis + structured fix
████░░░░░░░░░░░░░░░░  apply / verify loop
```

### Working today

- GitHub source fetch (tree + blobs)
- Path + content search
- Dart structural analysis (imports / implements / extends / mixes_in)
- Generic repository graph + structural expansion
- Dart lexical evidence analyzer (ownership, consumption, behavioral flow)
- Ranking / aggregation across signals
- `AnalyzeIssueService` orchestration (retrieval package)
- `IssueSignalExtractionService` — production signals from issue text via LLM
- `IssueDiagnosisService` — LLM diagnosis from the analysis package
- `IssueFollowUpService` — one question answered against a finished analysis
- `AnalysisRunner` — fetch → analyze → diagnose, for the HTTP layer. `POST /api/analyses` accepts optional `ref`/`commit`; the resolved SHA is stored as `commit_sha`. Language source at that SHA feeds ranking/diagnosis; a separate full tracked-file `snapshot` at the same SHA is kept for PatchValidator only.
- GitHub App user authorization + HttpOnly PatchPilot session. The demo repository is usable without login. User repositories require Connect GitHub and an App installation grant. Delivery uses installation tokens for granted repos and never a visitor-global write token.
- FastAPI: `/health`, auth, repositories, analyses, per-file source, questions, on-demand patch generate/validate/approve/deliver
- `frontend/` — Flutter web client with demo-first landing, diagnosis + patch review

### Stub / missing

- Sessions and analyses are in-memory: single worker only, lost on restart
- `worker/` is empty

---

## 2b. The web client

```text
Dashboard (Demo + Connect GitHub)  →  Issues  →  Diagnosis  →  Patch review  →  Code viewer
```

The product's claim is that a diagnosis is grounded in real code, so
**nothing in the diagnosis is a dead end.** Ranked files, individual
evidence rows, cited files and the suggested fix all open the source they
refer to, and evidence rows land on the exact line they came from.

After a completed diagnosis, `PatchPanel` is a separate review section
on the same screen: generate a proposal, inspect the file-grouped diff,
validate, approve on the server, then create a draft PR. Generation
success is never treated as a working patch. Approval does not create a
branch or PR; delivery does, and only for a repository the session is
authorized to write.

An analysis can pin a repository **ref/commit**. Leave it blank to
analyse current HEAD. An explicit SHA is resolved before the job starts
and shown on the diagnosis screen as "Analyzed at …". The issues list
has an optional commit field; the demo's Active filter issue (#3) can
be analysed at `f0bfc5b317f4984dc2c8d253715e9a30c72c0a5c`.

Each ranked file carries what put it there:

- direct evidence found in the file, with line numbers
- the structural edges that reached it
- how many of the issue's signals it matched

`AnalysisRunner._describe()` is the boundary that decides what the client
can see. It previously shipped a summary and discarded source and graph
edges, which made the UI unable to justify its own ranking — if you add a
new kind of evidence to the pipeline, surface it here or the client will
never show it.

### Root cause → exact code

The diagnosis names **symbols**; `DartSymbolLocator` decides where they
are. The model is never responsible for a location.

```text
LLM        → "CarsLoading", "LoadCars"       (naming: reliable)
locator    → car_state.dart:5, car_event.dart:3   (locating: deterministic)
```

This is the same split the pipeline uses everywhere: deterministic code
answers *where*, the model answers *why*. It is also the empirically
correct one — models cannot count lines and will assert a wrong one
confidently, but they quote a symbol from source accurately.

`symbols` is **optional and additive**. A diagnosis without it stays
valid and navigation falls back to whole files. The locator drops
anything it cannot resolve unambiguously — unknown names, external
types like `CircularProgressIndicator`, and names declared in more than
one file (`build`, `main`, `fetchCars`). A missing shortcut costs a
click; a wrong one sends a developer to the wrong code and discredits
the diagnosis.

Method declarations resolve too, and are excluded at call sites:
`dataSource.getCars()` never resolves, `Future<List<Car>> getCars()`
does.

### Two deliberate constraints

**Source is served per file** (`GET /api/analyses/{id}/files?path=`), not
embedded in the analysis payload, because that payload is polled
repeatedly while an analysis runs. The endpoint only serves files the
analysis actually ranked, so it cannot read arbitrary repository paths.

**Follow-up questions are stateless.** There is no transcript and no
memory between questions; each is answered against the analysis's own
evidence. That is what keeps an answer from drifting onto code the
pipeline never examined. Do not turn this into a chat without deciding
what replaces that guarantee.

---

## 3. Repository layout

```text
patchpilot/
├── CONTEXT.md                 ← this file (agent briefing)
├── PATCHPILOT.md              ← product vision / user flow
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI entry
│   │   ├── api/github.py      ← thin GitHub HTTP surface
│   │   ├── services/          ← language-agnostic pipeline services
│   │   └── utils/
│   │       ├── text_normalizer.py
│   │       ├── repository_graph.py
│   │       └── dart/          ← Dart-specific analyzers (first language pack)
│   ├── tests/
│   │   ├── test_dart_structure_analyzer.py
│   │   ├── test_analyze_issue_service.py
│   │   ├── test_task_diagnosis.py           ← controlled 3-case diagnosis benchmark
│   │   └── test_llm_end_to_end_diagnosis.py ← production-path integration (opt-in)
│   ├── pytest.ini
│   ├── requirements.txt
│   └── .env                   ← GITHUB_TOKEN, OPEN_AI_KEY (never commit)
├── worker/                    ← future apply/verify worker
└── evalutation/               ← evaluation (spelling as in repo)
    ├── snapshot.py            ← ONLY networked module; freezes a repo+issue fixture
    ├── pipeline.py            ← offline AnalyzeIssueService runner
    ├── score_ranking.py       ← scores ranked output against a ground-truth case
    ├── fixtures/              ← frozen repo snapshots (committed)
    └── cases/                 ← ground truth per issue
```

---

## 4. Pipeline (as implemented)

```text
GitHub Issue
    ↓
AnalyzeIssueService
    ├── IssueSignalExtractionService.extract_signals(title, body)
    │     (production: LLM; tests may inject IssueSignalService
    │      or pass signals= explicitly)
    ├── DartStructureAnalyzer.analyze_repository(files)
    ├── RepositoryGraph(relationships)
    ├── RepositoryEvidenceService.analyze_files
    └── per signal:
            RepositorySearchService.search / search_content
                ↓
            seed candidates
                ↓
            expand_candidates via graph (structural evidence)
                ↓
            RepositoryRankingService.rank(...)
                ↓
            aggregate → analysis package
                ↓
            IssueDiagnosisService.diagnose(analysis)
```

### Evidence priority (ranking philosophy)

```text
direct code evidence   ← strongest (declarations > usages > mentions)
direct content match
path evidence
structural evidence    ← weakest / supporting only
```

Ranking produces two components per file:

```text
direct_score + structural_score = total_score
```

**The three direct channels are not summed.** Path, content and evidence
are three observations of one fact — that a file is about a concept — so
adding them counts that fact three times. Each produces a confidence in
`[0, 1]` and they combine as independent partial observations:

```text
combined = 1 - Π (1 - reliability_c × confidence_c)

reliability:  evidence 1.00  >  path 0.45  >  content 0.30
```

Corroboration still helps, but each extra channel only claims a share of
what the previous ones left uncertain. The per-signal result is bounded
by the signal weight, so **a file cannot climb by shouting one concept —
it climbs by matching more of what the issue is about.** Summing across
*signals* in `aggregate()` is deliberate and is what rewards breadth.

This also makes content a genuine fallback for free: where evidence is
confident the residual is small, so content adds little; where no
language pack exists, content carries the file alone.

**Depth beats breadth.** Combined confidence is raised to
`CONFIDENCE_EXPONENT` (1.5) before weighting, so partial confidence across
many concepts is worth much less than high confidence on a few. Without
it a dependency-injection container — which references every concept the
app wires together and owns none of them — outranks the file that
implements the reported behaviour.

**Signal type is a prior on how diagnostic a kind of concept is:**

```text
behavior 4      names the SYMPTOM      "loading", "crash", "timeout"
architecture 3  names the LAYER        "repository", "bloc"
technology 2    names the STACK        "firebase", "postgres"
domain 1        names the ENTITY       "car", "user"
```

The bottom two are low for the same reason: a term describing the whole
repository cannot discriminate within it. In the demo repo `car` appears
in 89% of files and `firebase` in 28%, while `loading` appears in 17% and
points almost directly at the defect.

> **Measured and rejected: inverse document frequency.** Weighting each
> signal by `1 + log((N+1)/(df+1))` was implemented and measured as an
> alternative to the type prior above. It scored *worse*
> (tier-2-in-top-10 4/5 vs 5/5) and pushed the DI container from #5 to
> #2. On an 18-file corpus nearly every signal looks rare, so IDF mostly
> inflated all signals uniformly instead of discriminating, and it
> double-counted with the type prior, which already encodes "stack and
> entity terms are ubiquitous". Worth re-trying when the fixture set
> contains a repository large enough for `df` to mean something — but
> only with a before/after run.

`evidence_confidence` comes from language-pack `strength`. Occurrences of
the *same* evidence type saturate towards that type's strength, so fifty
weak identifier mentions can never outrank one class declaration.
Different evidence types still stack.

`structural_score` is dampened, decays with graph distance, and is capped
at 0.5x a file's own direct score. Dampening and the direct scale are
only meaningful relative to each other — **re-check both together
whenever either changes.**

`path_confidence` / `content_confidence` / `evidence_confidence` are also
reported per file. They are diagnostics that explain the direct score;
they do not sum to it.

Structural weights: `extends` = `implements` > `mixes_in` > `imports`.
A relationship type missing from `STRUCTURAL_WEIGHTS` scores zero, so any
new relationship the analyzer emits must be added there.

`RepositoryGraph.get_structural_relationships` reports every distinct
`(target, relationship)` pair, not merely every target. A file that is
both imported and implemented must surface both edges, otherwise the
weaker edge hides the stronger one.

Structural edges must be **legitimate language constructs**, never keyword/name similarity.
False structural edges contaminate ranking more than missing edges.
**Prefer conservative resolution over guessing.**

---

## 5. Module responsibilities

### Language-agnostic (keep them that way)

| Module | Role |
|--------|------|
| `GithubService` | Auth, issues, tree, blobs, source file download; `resolve_commit` pins a ref to a SHA |
| `AnalyzeIssueService` | Orchestrates signals → evidence → search → rank into an analysis package |
| `IssueSignalExtractionService` | Production: issue text → `{term, type}` signals via LLM |
| `IssueSignalService` | Hardcoded control/reference signals (deterministic ranking eval) |
| `IssueDiagnosisService` | Analysis package → structured LLM diagnosis |
| `PatchGeneratorService` | Issue + diagnosis + ContextPackage → structured patch proposal |
| `PatchValidatorService` | PatchProposal + full pre-fix file map → apply + command results |
| `FlutterValidationProfile` | Paths → runnable? + flutter pub get / analyze / test |
| `LLMService` | Thin OpenAI wrapper |
| `RepositorySearchService` | Path/content candidate retrieval |
| `TextNormalizer` | **Shared vocabulary layer.** Tokenization (camelCase, acronyms, separators) + conservative singularization + the `matches(term, text)` predicate |
| `RepositoryGraph` | Bidirectional graph over `{source, target, relationship}` |
| `RepositoryEvidenceService` | Combines language evidence analyzer + graph |
| `RepositoryRankingService` | Scores path / content / structural evidence |
| FastAPI / future orchestration | HTTP + analyze flow |

### Language boundary (`app/code_intelligence/`)

Context building must work for languages the Dart pack knows nothing
about, so it talks to code through one seam:

```text
ContextBuilderService          decides WHAT to include and HOW MUCH
        ↓
CodeIntelligence (Protocol)    the only language-aware boundary
        ↓
DartCodeIntelligence           adapter over the existing Dart pack
```

`CodeIntelligence` is a `Protocol`, not a base class — adapters inherit
nothing, and a test fake needs no import. Adapters exchange only the plain
records in `code_intelligence/types.py` (`Location`, `Span`, `Reference`);
nothing language-specific crosses.

**If the core ever needs to know a file is Dart, the boundary is in the
wrong place.** The core is tested against a fake adapter in no real
language, which is what keeps that honest.

`DartCodeIntelligence` is pure delegation to `DartStructureAnalyzer`,
`DartSymbolLocator`, `DartUsageAnalyzer` and `RepositorySearchService`. It
adds no analysis, so wrapping cannot change Dart behaviour — the parity
tests in `test_dart_code_intelligence.py` assert that against the real
fixtures. Keep them passing when touching either side.

Resolution stays conservative across the seam: `declaration_of` returns
`None` for a symbol that is unknown **or** ambiguous. Both are failures to
resolve. A missing location costs context; a wrong one sends a patch
generator at the wrong code.

`DartSpanLocator` answers where a declaration **ends** — the one capability
no existing component had, and the only new parsing in this layer. Brace
matching over masked source, so it is heuristic, and the rule is that an
uncertain answer is `None`: the caller falls back to a fixed window, which
costs context, whereas a wrong span silently truncates the code a patch is
reasoned about.

Three Dart-specific traps it handles, each with a test:

- **Named parameters are braces.** `CarBloc({required this.getCars})` ends
  the declaration at its own parameter list under naive counting. Braces
  inside parentheses are ignored.
- **Calls look like declarations.** `const Icon(Icons.error, size: 40),`
  matches the shared `Type name(` pattern. A signature followed by `,` or a
  closing bracket is refused — but **only in the signature**: applying that
  rule inside a body makes every `Text('a'),` in a list literal abandon the
  enclosing class.
- **Expression bodies have no brace.** `=> repository.fetch();` ends at the
  semicolon, as do abstract methods and fields.

Measured on all four fixtures: **545 of 566 declarations resolve to a span
(96%)**, and every decline is a call-shaped false positive from the shared
patterns — no real class or method loses its span. Re-run that sweep after
touching the locator; the failure mode is losing real declarations, and it
does not announce itself.

Known residual: `return Column(children: [` reads "return" as a return
type and yields a small bounded span attributed to `Column`. Fixing it
means filtering statement keywords in `DartSymbolLocator`, which changes
existing Dart behaviour.

`DartStructureAnalyzer.mask_source()`, `strip_comments()` and
`normalize_path()` are public. They were private helpers that the rest of
the Dart pack reached into anyway. The underscored spellings remain as
aliases and carry no behaviour — do not add new callers.

### Patch repair benchmark

`evalutation/patch_benchmark.py` measures whether a generated patch
**applies to the pre-fix tree and survives validation** — not whether it
reproduces the historical commit.

```bash
PYTHONPATH=backend python -m evalutation.patch_benchmark \
    --cases evalutation/cases/commit_grounded --proposals canned
PYTHONPATH=backend python -m evalutation.patch_benchmark \
    --cases evalutation/cases/commit_grounded --proposals generated
```

**A patch is not wrong for differing from the historical fix.** There are
many correct ways to fix a bug, and demanding one of them measures mimicry
rather than repair. The fix commit supplies supporting ground truth only —
which files a real fix touched — and recall/precision are diagnostics, not
the verdict. This is not hypothetical: on issue #1 the generator produces a
correct repair that is *not* byte-identical to the canned proposal.

Two proposal sources, never mixed, always recorded on the result:
`canned` holds the generator fixed so a failure is unambiguously
downstream; `generated` measures the real pipeline. **A canned pass says
the validator works; only a generated pass says PatchPilot repaired
anything.**

Cases are classified by how far they got — `generation_failure`,
`proposal_invalid`, `apply_failure`, `validation_failure`, `passed` — so an
unavailable model is visible as its own stage rather than scored as a bad
patch.

> **Validation currently proves the path, not compilation.** Committed
> pre-fix fixtures are still source-only (they have not been
> re-snapshotted). `FlutterValidationProfile` requires `pubspec.yaml`
> at the repo root before it emits `flutter pub get` / `analyze` /
> `test`. Against today's fixtures the profile reports not runnable and
> the harness runs no commands. **Do not read a PASS without commands
> as "the code compiles."** Re-snapshot with
> `get_repository_tracked_files` when a runnable workspace is needed.

The snapshotter itself is language-agnostic: UTF-8 git blobs under a
size cap, no `if Flutter: include pubspec.yaml`. Production analysis
still fetches source extensions only.

Baseline, both sources, all three cases: 3/3 generated, 3/3 applied, 3/3
validated (fake runner), file recall and precision 1.00.

### ContextBuilderService

Selects the code a patch generator needs. Performs no retrieval and calls
no model — which files are relevant was decided by ranking, which has a
benchmark behind it.

Candidates are collected in tier order, and **eviction is the same list
read backwards**, so a plan can be truncated anywhere and remain the best
context available at that size:

```text
0 defect       the declaration the diagnosis named
1 supporting   declarations it referenced
2 dependency   what the defect imports
3 caller       symbol references first, then bare importers
4 contract     implements / extends, in BOTH directions
5 test         tests that reach the changed code
6 secondary    whatever else ranking surfaced
```

Two dedup rules, both load-bearing. Symbol-anchored candidates are distinct
within a file, so a defect and a supporting declaration can share one.
File-level candidates collapse against any path already present: once a
file is in for a strong reason, adding it again for a weaker one says
nothing new.

**Tests are confined to tier 5.** A test importing the defect otherwise
arrives as a *caller* first, which over-prioritises it and lets it escape
the separate cap the test tier exists to impose.

The core is tested against a `FakeCodeIntelligence` over files in a
language that does not exist. If a test there ever needs Dart, the
abstraction has leaked — that suite is what makes future adapters cheap.

`build()` turns the plan into a `ContextPackage`: enclosing span or a
fixed fallback window, padded, with the file header unioned in; overlapping
or near-adjacent slices in one file merge; a file collapses to whole-file
when retained lines cross a configurable fraction. `ContextBudget` then
evicts reverse-tier (T0 is never cut). Defaults are provisional
(`max_files=12`, `max_lines_total=1200`, `max_lines_per_file=400`,
`max_tests=2`) and are not tuned against the commit-grounded cases.

Language is not assumed. `CodeIntelligenceRegistry` selects an adapter
per file by extension (`.dart` → `DartCodeIntelligence`; anything else
→ `NullCodeIntelligence`). The null adapter answers every protocol
method conservatively so an unsupported language still yields a
file-level package. Slices record their own `language` and `adapter`; a
mixed repository is labelled `mixed` at package level. The builder never
imports Dart.

> **Symbol resolution.** `DartSymbolLocator` treats a class and its
> constructor as one declaration, and prefers a product-code site over a
> test-file match. Genuinely ambiguous product declarations still resolve
> to none. Constructor calls (`const Foo()`, `return Foo()`) are not
> indexed as functions.

### PatchGeneratorService

Turns bounded context into a structured patch proposal. Performs no
retrieval, no ranking, and no repository access — if a path is not in
`ContextPackage.slices`, it cannot be edited.

```text
issue + diagnosis + ContextPackage  →  PatchProposal
                                              ↓
                               PatchValidator (offline; not API-wired)
```

Input is exactly `(issue, diagnosis, context_package)`. Diagnosis
`suggested_fix` is guidance in the prompt, not a patch. Slice `content`
is the only editable truth; hunk `old_text` must match the context-
derived span for `[start_line, end_line]` after the same
`splitlines()` / `"\n".join` normalization ContextBuilder uses.

**Output contract.** `PatchProposal` carries `status`, prose fields,
and `files[]` of `PatchHunk` records (`start_line`, `end_line`,
`old_text`, `new_text`). Status values: `ok`, `insufficient_context`,
`ambiguous`, `invalid`, `empty`. `to_json()` uses `sort_keys=True` for
snapshot tests.

**Validation is two-stage.** The model response is parsed like diagnosis
(strip fences → `json.loads` → hand-written schema check). Hunks are then
context-anchored: path must appear in slices, every line in the range
must be covered, `old_text` must match exactly, and overlapping hunks in
one file are rejected. Parse failures return `status=invalid` as a
proposal — they do not raise — so a runner can keep diagnosis and
context alongside the failure.

**Wired on demand.** `AnalysisRunner` builds and stores a
`ContextPackage` after diagnosis. Patch generation is not part of the
analysis job itself — `POST /api/analyses/{id}/patch` calls
`PatchGeneratorService` with the stored issue, diagnosis, and context
only. The proposal is kept on the job as `patch_proposal` /
`patch_error` and served from `/patch`, never from the polling
`Analysis` payload.

**Review UI.** The diagnosis screen keeps its existing layout. After a
completed diagnosis, `PatchPanel` calls generate/get `/patch`, renders
hunks as a file-grouped diff, then `POST /patch/validate`. Approval is
session-local UI state. No branch, commit, or GitHub PR.

### PatchValidatorService

Applies a `PatchProposal` against a **full pre-fix file snapshot**, not
ContextPackage slices. Deterministic: no LLM, no GitHub, no ranking.

```text
PatchProposal + file map + ValidationConfig  →  PatchValidationResult
```

Hunk `old_text` must match the full file at `[start_line, end_line]`
after the same `splitlines()` / `"\n".join` normalization. Hunks in one
file are applied in reverse `start_line` order. The original snapshot
map is never mutated; files are copied into a temp workspace, patched,
optionally checked with operator-supplied argv, then the workspace is
removed.

**Statuses.** `proposal_invalid` (malformed, overlap, unsafe path,
non-ok proposal), `apply_failed` (missing path, stale `old_text`),
`validation_failed` (apply succeeded; command non-zero or timeout),
`passed` (apply succeeded; commands exit 0, or none were configured).
Success is not byte-identity with a historical fix commit.

**Commands** go through `ValidationCommandRunner`. Tests use
`FakeValidationCommandRunner`. `ShellValidationCommandRunner` runs argv
with timeout and bounded logs (`shell=True` is never used).
`FlutterValidationProfile` inspects the file map and, when
`pubspec.yaml` is present, supplies `flutter pub get` / `analyze` /
`test`. The snapshotter does not know Flutter.

**Wired on demand.** `POST /api/analyses/{id}/patch/validate` applies
the stored proposal against the job's **full pinned snapshot**
(`snapshot` / `snapshot_commit`), not ranked `sources`. Ranked sources
stay top-10 for the diagnosis UI and `GET /files`. When
`FlutterValidationProfile` finds `pubspec.yaml` in the snapshot, it
runs flutter pub get / analyze / test. The result is stored as
`patch_validation` / `patch_validation_error` and served from
`/patch/validate`, never from the polling `Analysis` payload. A
snapshot SHA that does not match `commit_sha` is refused. No branch,
commit, or GitHub PR.

### Language-specific (Dart today)

| Module | Role |
|--------|------|
| `DartStructureAnalyzer` | Real Dart constructs → file relationships |
| `DartEvidenceAnalyzer` | Lexical evidence vs signals (does **not** decide relevance) |
| `DartUsageAnalyzer` | Cross-file type usage: who CONSUMES what another file DECLARES; same-file type families for behavioral flow |

### Relevance is not only ownership

Scoring rewards a file for **owning** a concept — declaring the class,
defining the function. That misses a whole category of relevant file:

```text
car_state.dart        declares  CarsLoading      ← owner
car_list_screen.dart  reacts to CarsLoading      ← consumer, owns nothing
```

For "the loading indicator never goes away", the screen branching on that
state is what a developer opens first, yet it declares nothing.

`DartUsageAnalyzer` resolves cross-file type references and reports **how**
each type is used. The evidence analyzer then upgrades a resolved
reference from `identifier` (0.2) to `consumes` (0.7), *replacing* the
identifier record — one occurrence is one observation.

**Only `state_test` counts.** The detector also reports `type_argument`
and `reference`, but they are not accepted as evidence:

> **Measured and rejected: counting every resolved reference.** Accepting
> all kinds promoted `injection_container.dart` from #8 to **#3** and
> `main.dart` from #7 to #4, while the actual consumer did not move at
> all. Assembling an application means referencing more types than
> anything else does, so "references a relevant thing" became "is
> relevant" — the exact failure the mechanism exists to avoid. Adding
> `type_argument` breaks the same way at higher strengths. Widening
> `CONSUMPTION_KINDS` requires a before/after run on both cases.

> **Phase 4 — measured partial success.** Consumption moved
> `car_list_screen.dart` from #9 to #6 against `baseline_phase3.json`.
> Metrics stayed at tier-1-in-top-5 **4/5**: the screen is still
> outside the window, and the abstract repository contract occupies
> slot #5. The ground truth is not the problem — the screen belongs
> in tier 1. Raising `consumes` from 0.7 to 1.0 produces an identical
> ranking, because confidence saturates. More volume on the same
> evidence type cannot close the remaining gap.

The `consumes` strength is not finely tuned: any value from 0.7 up to 1.0
produces an identical ranking, because confidence saturates. **Do not
raise it further.**

### Behavioral flow is not the same as consuming one type

`consumes` only fires when the identifier itself matches a signal.
`CarsLoading` matches "loading"; `CarsLoaded` and `CarsError` do not.
A screen that branches on all three is the UI for that behaviour's
lifecycle, yet Phase 4 only credits the one type whose name contains
the symptom.

```text
car_state.dart        declares  CarsLoading, CarsLoaded, CarsError
car_list_screen.dart  reacts to all three          ← the loading UI
```

Detection stays in the Dart pack: `type_families()` groups classes that
share a base **declared in the same file**, and a file that `state is`
tests two or more members of a family — including one whose name
matches a **behavior** signal — emits `behavior_flow`. Ranking never
sees the family. It receives the same generic record shape as every
other evidence type (`evidence_type`, `concept`, `strength`).

This is a new *kind* of observation, not a louder `consumes`. Distinct
types stack, which is why it can move a file after consumption has
saturated. A file that only tests `CarsLoading` still gets `consumes`
alone. A widget that only handles Loaded/Error does not get loading
flow. Constructing or emitting the states (the BLoC, the DI container)
is not a reaction.

> **Phase 5 — measured success.** Against `baseline_phase4.json`,
> `car_list_screen.dart` moved **#6 → #1** and tier-1-in-top-5 went
> **4/5 → 5/5**. The abstract repository contract dropped from #5 to
> #6 (its ground-truth tier). No distractor entered the top 5.
> Within-tier order now places the observing screen above the BLoC
> that owns the machine; the case treats that order as informational
> only. Strength was not fitted: 0.8 is the midpoint between
> `consumes` and a function declaration.
>
> The synthetic Stripe case was observed, not calibrated against.
> `checkout_screen.dart` moved #5 → #1 (the mechanism transfers).
> Metrics stayed 4/5 because `stripe_payment_gateway.dart` was already
> outside the window at Phase 4. Do not retune `behavior_flow` to
> chase that fixture.

### Matching contract (do not redesign casually)

Every channel that asks "does this text mention this concept" — path
search, content search, and each language pack's evidence analyzer —
must answer through `TextNormalizer.matches()`. If two channels disagree,
one invents candidates the other cannot see and ranking becomes
uncalibratable.

Matching is on **tokens**, never substrings, and both sides are
singularized:

```text
"car" matches CarRepository   [car, repository]
"car" matches getCars         [get, car]     ← plural; code says Cars, issues say car
"car" REJECTS MoreCard        [more, card]   ← the substring trap
```

Both halves are load-bearing. Substring matching lets the payment-card
UI become evidence for the car domain; strict token matching without
singularization loses `getCars` / `fetchCars` / `LoadCars`, i.e. the
entire call chain. Removing either rule regresses retrieval — measure
with the evaluation harness before touching it.

### Relationship contract (do not redesign casually)

```python
{
    "source": "lib/data/repositories/car_repository_impl.dart",
    "target": "lib/domain/repositories/car_repository.dart",
    "relationship": "implements"  # imports | implements | extends | mixes_in
}
```

Only create a relationship when the **target exists in the supplied repository files**.
Never create edges to external packages (`flutter_bloc`, `cloud_firestore`, etc.).

---

## 6. DartStructureAnalyzer — critical rules

`DartStructureAnalyzer` builds a **trustworthy structural map**. It does **not** diagnose bugs or rank files.

It must understand constructs like:

```dart
import ...
class A implements B
class A extends B
class A with B
```

It must **not** say: “both files contain `car`, therefore they are related.”

### Required behaviors

1. Resolve relative imports from the importing file.
2. Resolve internal `package:<app>/...` → `lib/...` when that file exists.
3. Ignore `dart:` and unresolved external packages.
4. Resolve `implements` / `extends` / `mixes_in` only when the referenced type can be tied to an explicit local import (or equally unambiguous resolution). **Do not guess.**
5. Ignore comments and string literals.
6. Do not turn generic type arguments into relationship targets.
7. Preserve `{source, target, relationship}` output.

### Unit tests

Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q tests/test_dart_structure_analyzer.py
```

These tests encode the design. Prefer fixing the analyzer over weakening the tests.

Demo repo often used in harnesses: `SanjayKParida/car-rental-app` (hyphens, not underscores).

---

## 7. Multi-language strategy (3–4 languages)

Architecture goal: **language-agnostic core + language packs**.

```text
Search · Graph · Evidence façade · Ranking · Orchestration · LLM
                         │
              LanguageAnalyzer registry
                         │
        Dart · Python · TypeScript/JS · Kotlin/Java
```

### Plugin contract (target shape)

Each language pack should provide roughly:

- `extensions` — e.g. `(".dart",)` / `(".py",)` / `(".ts", ".tsx", ".js")`
- `analyze_structure(files) → relationships`
- `analyze_evidence(file, signals) → evidence`
- `classify_line(line) → code|import|comment`
- `is_test_file(path) → bool`

### Suggested order

1. Finish packaging Dart behind a clear interface (already mostly done).
2. Python (simple imports / inheritance).
3. TypeScript/JavaScript.
4. Kotlin or Java.

### Rules for multi-language work

- Ranking must **not** branch on language name; it consumes shared relationship vocabulary.
- Unknown language → degrade to path/content search only (empty/partial graph OK).
- Extract Dart-specific bias out of shared services over time (e.g. test suffixes, `//` comment detection in search).
- New language packs match concepts via `TextNormalizer`, never with their own ad-hoc string comparison.
- Do **not** wait for perfect ASTs; conservative lexical/regex analyzers are acceptable for MVP.

---

## 8. What agents should / should not change

### Safe / preferred focus areas

- Language analyzers under `backend/app/utils/<lang>/`
- New *kinds* of evidence (as opposed to new weights) — ownership,
  consumption, and behavioral flow are the current split; a further
  kind needs a before/after against `evalutation/baseline_phase5.json`
- `POST /analyze` HTTP API on top of `AnalyzeIssueService`
- Unit tests for analyzers

### Do not casually rewrite

Unless the task explicitly requires it:

- `RepositoryGraph` contract
- Ranking evidence hierarchy (structural must stay weaker than direct)
- The channel-combination rule (never sum path + content + evidence)
- Relationship dict shape `{source, target, relationship}`

### Do not compensate for bad structure in ranking

If the graph has false edges, **fix the structure analyzer**. Do not paper over bad edges by tuning ranking weights.

### Secrets

- Never commit `.env`, tokens, or credentials.
- Backend expects `GITHUB_TOKEN` in `backend/.env`.

---

## 9. How to run things

```bash
cd backend
source .venv/bin/activate   # or use .venv/bin/python directly

# Deterministic suite (no API keys, no network)
# Default pytest already excludes @pytest.mark.integration
PYTHONPATH=. python -m pytest -q

# Real-LLM / GitHub integration tests (needs OPEN_AI_KEY + GITHUB_TOKEN)
PYTHONPATH=. python -m pytest -q -m integration
```

### Ranking evaluation (offline, from the repo root)

Calibration must be measured, not eyeballed. The evaluation harness runs
the pipeline against a frozen snapshot so runs are deterministic and
comparable.

```bash
# from the repo root, NOT backend/
PYTHONPATH=backend python -m evalutation.score_ranking
PYTHONPATH=backend python -m evalutation.score_ranking --case payment_pending

# save / compare a baseline around a scoring change
PYTHONPATH=backend python -m evalutation.score_ranking --baseline before.json
PYTHONPATH=backend python -m evalutation.score_ranking --compare before.json

# re-freeze the snapshot (network; do this deliberately)
PYTHONPATH=backend python -m evalutation.snapshot \
    --owner SanjayKParida --repo car-rental-app

# freeze an explicit commit
PYTHONPATH=backend python -m evalutation.snapshot \
    --owner O --repo R --commit <sha>

# freeze the state BEFORE a fix landed (for real-world benchmarking)
PYTHONPATH=backend python -m evalutation.snapshot \
    --owner O --repo R --parent-of <fix-sha> \
    --out evalutation/fixtures/<name>_pre_fix.json
```

### Finding benchmark candidates

```bash
PYTHONPATH=backend python3 -m evalutation.discover_cases \
    --owner O --repo R --limit 20
```

Finds `(closed issue, fixing commit)` pairs and prints them with the
evidence for each. It **proposes; it does not create** — review the
candidates, then hand the good ones to `generate_case.py`. A wrong
guess costs a line of output rather than a fixture that looks valid.

Evidence, strongest first: a timeline `closed` event carrying a
`commit_id`, then a `referenced` commit whose message closes the issue.
Rule 5 (diff touches product Dart) reuses `ground_truth`, so discovery
and scoring cannot disagree about what counts as product code.

> **Measured yield is currently near zero, and this is the blocker for
> harvesting real cases.** How Dart repositories actually close issues:
>
> | repo | closed by commit | cross-referenced PR | neither |
> |---|---|---|---|
> | `felangel/bloc` | 0% | 0% | 100% |
> | `flutter/samples` | 25% | 0% | 75% |
>
> Most issues are closed by hand with no machine-readable link at all.
> Two further obstacles found on real repositories:
>
> - **Closed PRs outnumber closed issues ~9:1**, so scanning must skip
>   them before they consume the budget (fixed; `examined` counts real
>   issues only).
> - **`referenced` commits often live in contributors' forks** and 422
>   against the upstream repo. Skipped by design.
> - **Monorepos defeat the `lib/` rule.** In `flutter/samples`, product
>   code is `<project>/lib/...`, so `ground_truth.PRODUCT_ROOT`
>   ("starts with `lib/`") matches nothing. Changing it to "contains a
>   `lib/` segment" would fix that, but `ground_truth` is deliberately
>   frozen — decide before harvesting from a monorepo.
> - **Fixes must be localised.** `flutter/samples` #2818 closed with a
>   250-file maintenance commit; `--max-files` (default 5) rejects
>   those, because scoring retrieval against a repo-wide sweep measures
>   nothing.

### Adding a benchmark case

```bash
PYTHONPATH=backend python3 -m evalutation.generate_case \
    --owner O --repo R --issue-number N --fix-commit <full-sha>
```

Writes both halves — `fixtures/<name>_pre_fix.json` and
`cases/commit_grounded/<name>.json` — and pins freshly extracted
signals. Composes `ground_truth.derive_ground_truth`,
`snapshot.capture` and `IssueSignalExtractionService`; adds no logic.

It refuses rather than emitting a case that cannot be scored:

- the fix changes no product source file (nothing to find)
- the fix commit has no parent (no pre-fix state)
- the snapshot is not the fix's parent (code and answer disagree —
  the exact pairing bug that produced a bad fixture once already)
- signal extraction fails or returns nothing (case would not be
  reproducible)
- the fixture or case already exists, without `--force`

Ground truth is derived **before** anything is downloaded, so an
unscoreable case costs no snapshot.

**Review the pinned signals after generating.** They are one model
sample, not a reviewed set.

### Commit-grounded benchmark

```bash
PYTHONPATH=backend python3 -m evalutation.commit_benchmark \
    --cases evalutation/cases/commit_grounded
```

Runs the real pipeline against a pre-fix snapshot and scores it against
what the fix commit actually changed. Ground truth is derived, not
hand-labelled. Add a case by dropping a JSON file into the directory;
the runner has no built-in knowledge of which cases exist.

**Cases pin their signals, and must.** Signal extraction is a model
call: the same case measured rank 3, 1, 1 on three identical runs,
flipping recall@1 between 0.00 and 1.00. With signals pinned, RANK and
recall@k are reproducible. A test enforces that every committed case
pins signals and records why.

What is still stochastic: everything downstream of
`IssueDiagnosisService` — root cause, cited files, PREC and the
PASS/FAIL verdict. The rollup footer labels which half is which. Do
not read a PREC change between two runs as a regression.

`--extract-signals` bypasses the pinned set to measure extraction end
to end. Never use it for a before/after comparison.

> **Known, not fixed:** files with *equal* scores change places between
> runs, because Python randomises string hashing per process and the
> ranking sort has no tie-break. It moves no metric — only display
> order below the top few. The fix is a secondary sort key on `path` in
> `AnalyzeIssueService._build_ranked_output`.

`--parent-of` is the one that matters for benchmarking against real
closed issues: the repository must be frozen as it was *before* the
fix, or the defect is not present to find.

`GithubService.get_repository_tree` / `get_repository_source_files`
take an optional `ref`. Omitting it keeps the default-branch
behaviour every other caller depends on. **A caller that resolves a
commit must pass that ref through to the file fetch** — resolving a
SHA and then reading the default branch produces a fixture labelled
with an old commit but containing today's code, which looks valid and
silently measures the wrong thing.

`evalutation.snapshot.capture` uses `get_repository_tracked_files`:
UTF-8 blobs at that ref, size-capped, no language include-list.
Analysis still uses `get_repository_source_files` so ranking does not
ingest lockfiles. After a re-snapshot, pass the full map to the
validator and keep source-filtered files for ranking — do not mix
those jobs in the snapshotter.

**Rule: no scoring weight changes without a before/after run.**
Current retrieval baseline: `evalutation/baseline_phase5.json`.

Two cases exist. `cars_loading` runs against a real repository and is the
primary measurement. `payment_pending` is a **synthetic** fixture that
mirrors the same architecture with entirely different vocabulary; it
exists only to check that a mechanism generalizes rather than fitting the
first case. Treat it as the weaker evidence it is, and never tune against
it.

`evalutation/pipeline.py` runs retrieval through `AnalyzeIssueService`
with `IssueSignalService` (or a case's manual `signals=`) so ranking
eval stays independent of the LLM.

Import path note: run from `backend/` with `PYTHONPATH=.` so `app.*` imports resolve.
Do not run modules from `backend/tests/` as a bare script unless `PYTHONPATH` includes `backend/`.

---

## 10. Planned analyze API contract

From product design — not fully implemented yet:

**Input:** `repositoryId`, `issueId` (GitHub auth handled by backend).

**Output (target):**

```json
{
  "issueId": "",
  "description": "",
  "cause": "",
  "relatedFiles": [],
  "evidence": [],
  "proposedChanges": [],
  "tests": [],
  "status": ""
}
```

When implementing LLM diagnosis, constrain the model with ranked files + evidence; require structured output matching this shape.

---

## 11. Known gaps / risks agents should know

1. **LLM signal extraction is not yet measured as a ranking gate** — production uses `IssueSignalExtractionService`; ranking eval still injects manual/`IssueSignalService` signals. Do not retune ranking against LLM-extracted terms.
2. **Within-tier order is not a retrieval target** — Phase 5 put the observing screen above the owning BLoC. That is allowed by the case; do not retune evidence strengths to restore a preferred order inside a tier.
3. **No `POST /analyze` yet** — orchestration exists as `AnalyzeIssueService`; HTTP still only exposes GitHub issue listing.
4. **Full-repo blob download every run** — fine for MVP demos; needs caching by commit SHA before production.
5. **Hub problem** — widely imported models can flood structural expansion; ranking already treats structural evidence as weak — keep it that way.

---

## 12. One-sentence north star

**PatchPilot turns a GitHub issue into a small, evidence-backed code context so an LLM can diagnose and propose a fix — retrieval stays deterministic and multi-language-ready; reasoning stays LLM-bound and constrained.**
