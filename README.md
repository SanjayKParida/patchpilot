# PatchPilot

Point PatchPilot at a GitHub repository, pick an issue, and get a root-cause
diagnosis grounded in the repository's own code.

```text
Dashboard  →  Issues  →  Diagnosis  →  Code viewer
```

Nothing in the diagnosis is a dead end: ranked files, evidence lines, cited
files and the suggested fix all open the code they refer to.

Retrieval is deterministic and code-aware; the language model only reasons
about the small set of files retrieval ranked highest. See `CONTEXT.md` for
the engineering context and `PATCHPILOT.md` for the product notes.

---

## Requirements

- Python 3.12+ and the virtualenv in `backend/.venv`
- Flutter 3.44+ with web enabled
- `backend/.env` containing:

  ```dotenv
  GITHUB_TOKEN=<a token with repo read access>
  OPEN_AI_KEY=<an OpenAI API key>
  ```

  Without `OPEN_AI_KEY` the API still runs, but analyses return ranked
  files with a `diagnosis_error` instead of a diagnosis. Retrieval does
  not need a model.

---

## Run it

**API** — from `backend/`:

```bash
PYTHONPATH=. .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Interactive docs at http://127.0.0.1:8000/docs.
`GET /health` reports whether GitHub and diagnosis are configured.

> Analyses are held in memory, so run a **single** worker. Restarting the
> API discards in-flight and completed analyses; they are cheap to re-run.

**Web client** — from `frontend/`:

```bash
flutter run -d chrome
```

Point it at a different API with
`--dart-define=API_BASE_URL=http://host:8000`.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Readiness and configuration |
| `GET` | `/api/repositories?url=` | Validate a pasted repo URL, return metadata |
| `GET` | `/api/repositories/{owner}/{repo}/issues?search=` | List issues, pull requests excluded |
| `POST` | `/api/analyses` | Start an analysis, returns `202` and a job |
| `GET` | `/api/analyses/{id}` | Poll status and results |
| `GET` | `/api/analyses/{id}/files?path=` | Source of one ranked file |
| `POST` | `/api/analyses/{id}/questions` | One question about a completed analysis |

An analysis downloads repository source and calls a language model, so it is
a background job rather than a blocking request. `status` moves through
`queued → running → completed | failed`, and `stage` names the pipeline step
the UI displays.

A completed analysis carries `signals`, `relevant_files` (ranked, each with
the evidence that placed it there), and `diagnosis` (`root_cause`,
`confidence` as a probability in `[0, 1]`, `explanation`, `suggested_fix`,
and the `relevant_files` the diagnosis actually leans on).

The diagnosis carries `symbols` it reasoned about and `locations` —
those symbols resolved to `path`, `line` and declaration kind. The model
names them; the analyzer locates them. Symbols that cannot be resolved
unambiguously are dropped, and navigation falls back to whole files.

Each ranked file carries the evidence that placed it there: the direct
evidence found in the file (with line numbers) and the structural edges
that reached it. The client uses those to answer "why this file?" and to
jump straight to the line an item came from.

Source is served **per file**, not inside the analysis payload — that
response is polled repeatedly while an analysis runs. Only files the
analysis actually ranked can be fetched, so the endpoint cannot be used to
read arbitrary paths from the repository.

Follow-up questions are stateless. Each is answered against the analysis's
own evidence with no conversation history, which is what keeps an answer
from drifting onto code the pipeline never looked at.

Retrieval and diagnosis fail independently: if the model call fails, ranked
files are still returned and `diagnosis_error` explains what went wrong.

---

## Layout

```text
backend/app/
  api/                    HTTP surface only
  dependencies.py         composition root
  services/
    analyze_issue_service.py       retrieval + ranking pipeline
    issue_signal_extraction_service.py
    issue_diagnosis_service.py
    analysis_runner.py             fetch -> analyze -> diagnose, for HTTP
    analysis_store.py              in-memory job registry
  utils/dart/             Dart language pack
frontend/lib/
  models/         API contract
  services/       API client, recent repositories
  screens/        dashboard, issues, diagnosis, code viewer
  widgets/        shared UI, why-this-file, follow-up
evalutation/      offline ranking evaluation (see CONTEXT.md)
```
