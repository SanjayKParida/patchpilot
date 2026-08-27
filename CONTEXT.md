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
    → (later) apply in isolation + verify with tests
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
░░░░░░░░░░░░░░░░░░░░  apply / verify loop
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
- `AnalysisRunner` — fetch → analyze → diagnose, for the HTTP layer
- FastAPI: `/health`, repositories, analyses, per-file source, questions
- `frontend/` — Flutter web client

### Stub / missing

- No apply-fix / run-tests workspace yet
- `worker/` is empty
- Analyses are held in memory: single worker only, lost on restart

---

## 2b. The web client

```text
Dashboard  →  Issues  →  Diagnosis  →  Code viewer
```

The product's claim is that a diagnosis is grounded in real code, so
**nothing in the diagnosis is a dead end.** Ranked files, individual
evidence rows, cited files and the suggested fix all open the source they
refer to, and evidence rows land on the exact line they came from.

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
| `GithubService` | Auth, issues, tree, blobs, source file download |
| `AnalyzeIssueService` | Orchestrates signals → evidence → search → rank into an analysis package |
| `IssueSignalExtractionService` | Production: issue text → `{term, type}` signals via LLM |
| `IssueSignalService` | Hardcoded control/reference signals (deterministic ranking eval) |
| `IssueDiagnosisService` | Analysis package → structured LLM diagnosis |
| `LLMService` | Thin OpenAI wrapper |
| `RepositorySearchService` | Path/content candidate retrieval |
| `TextNormalizer` | **Shared vocabulary layer.** Tokenization (camelCase, acronyms, separators) + conservative singularization + the `matches(term, text)` predicate |
| `RepositoryGraph` | Bidirectional graph over `{source, target, relationship}` |
| `RepositoryEvidenceService` | Combines language evidence analyzer + graph |
| `RepositoryRankingService` | Scores path / content / structural evidence |
| FastAPI / future orchestration | HTTP + analyze flow |

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
```

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
