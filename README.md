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
- `backend/.env` containing at least:

  ```dotenv
  OPEN_AI_KEY=<an OpenAI API key>
  DEMO_OWNER=SanjayKParida
  DEMO_REPO=patchpilot-diagnosis-demo
  ```

  Without `OPEN_AI_KEY` the API still runs, but analyses return ranked
  files with a `diagnosis_error` instead of a diagnosis. Retrieval does
  not need a model.

### GitHub credentials

There are two separate GitHub identities. Do not use one as a fallback
for the other.

**Demo repository (anonymous visitors)**

```dotenv
GITHUB_TOKEN=<a fine-grained or classic token that can READ the demo repo>
```

This token is isolated to `DEMO_OWNER`/`DEMO_REPO`. It is used so anyone
can open the demo, list issues, analyze, generate a patch, and validate
without logging in. It is **never** used to open a pull request on behalf
of a visitor, and it is never used for a visitor's own repositories.

**User repositories (Connect GitHub)**

Create a GitHub App and set:

```dotenv
GITHUB_APP_ID=<numeric app id>
GITHUB_APP_CLIENT_ID=<iv1. …>
GITHUB_APP_CLIENT_SECRET=<app client secret>
GITHUB_APP_PRIVATE_KEY=<PEM, newlines as \n>
GITHUB_APP_SLUG=<app slug from the public page, e.g. patchpilot>
GITHUB_APP_REDIRECT_URI=http://localhost:8000/api/auth/github/callback
SESSION_SECRET=<long random string>
FRONTEND_ORIGIN=http://localhost:XXXX
```

Use `localhost` (not `127.0.0.1`) for the API, the Flutter app, and the
callback so the session cookie is sent. The Flutter client defaults to
`http://localhost:8000`.

GitHub App permissions (Repository, no unused org scopes):

| Permission | Access | Why |
|---|---|---|
| Metadata | Read | Required by GitHub Apps |
| Contents | Read and write | Source, blobs, trees, commits, branches |
| Issues | Read | Issue list and bodies |
| Pull requests | Read and write | Draft PRs |

In the App settings:

1. Callback URL = `GITHUB_APP_REDIRECT_URI`
2. Setup URL = the same callback
3. Enable **Request user authorization (OAuth) during installation**
4. Enable **Expire user authorization tokens** if offered (refresh is stored server-side)

After a user authorizes and selects repositories, PatchPilot stores the
PatchPilot session in an **HttpOnly** cookie. GitHub access tokens never
leave the API process: not in JSON, not in `localStorage`.

Opening a draft PR uses an **installation access token** for a repository
the user actually granted. If they cannot write, delivery fails with a
permission message and does not fall back to `GITHUB_TOKEN`.

Local evaluation without a GitHub App still uses `GITHUB_TOKEN` for any
repo, matching the previous single-token setup. As soon as
`GITHUB_APP_CLIENT_ID` is set, that fallback is gone.

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
`--dart-define=API_BASE_URL=http://localhost:8000`.

Keep the browser on `http://localhost:…` as well. Mixing `localhost` and
`127.0.0.1` drops the session cookie.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Readiness and configuration |
| `GET` | `/api/auth/me` | Current PatchPilot session (no GitHub tokens) |
| `GET` | `/api/auth/github/login` | Start GitHub App authorization (returns URL) |
| `GET` | `/api/auth/github/callback` | OAuth callback; sets HttpOnly session cookie |
| `POST` | `/api/auth/logout` | Invalidate the session |
| `GET` | `/api/repositories/demo` | Configured demo repository (no login) |
| `GET` | `/api/repositories/authorized` | Repos the current user granted the App |
| `GET` | `/api/repositories?url=` | Validate a repo the caller is allowed to use |
| `GET` | `/api/repositories/{owner}/{repo}/issues?search=` | List issues, pull requests excluded |
| `POST` | `/api/analyses` | Start an analysis, returns `202` and a job |
| `GET` | `/api/analyses/{id}` | Poll status and results |
| `GET` | `/api/analyses/{id}/files?path=` | Source of one ranked file |
| `POST` | `/api/analyses/{id}/questions` | One question about a completed analysis |
| `POST` | `/api/analyses/{id}/patch` | Generate or return the stored patch proposal |
| `GET` | `/api/analyses/{id}/patch` | Return a stored patch proposal |
| `POST` | `/api/analyses/{id}/patch/validate` | Apply the stored proposal and run Flutter checks |
| `GET` | `/api/analyses/{id}/patch/validate` | Return a stored validation result |
| `POST` | `/api/analyses/{id}/patch/approve` | Record server-side approval of the stored patch |
| `GET` | `/api/analyses/{id}/patch/approve` | Return a stored approval |
| `POST` | `/api/analyses/{id}/patch/deliver` | Open a draft PR from the approved patch |
| `GET` | `/api/analyses/{id}/patch/deliver` | Return the latest delivery attempt |

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
  application/            auth + delivery use-cases
  domain/                 auth + delivery types (no HTTP/GitHub)
  infrastructure/         GitHub App client + write client
  config.py               env: GitHub App, session, demo repo
  dependencies.py         composition root
  services/
    analyze_issue_service.py       retrieval + ranking pipeline
    issue_signal_extraction_service.py
    issue_diagnosis_service.py
    analysis_runner.py             fetch -> analyze -> diagnose, for HTTP
    analysis_store.py              in-memory job registry
    auth_store.py                  users, sessions, authorized repos
    github_service.py              read-only GitHub GET API
  utils/dart/             Dart language pack
frontend/lib/
  models/         API contract
  services/       API client (cookie credentials), recent repositories
  screens/        dashboard, issues, diagnosis, code viewer
  widgets/        shared UI, why-this-file, follow-up
evalutation/      offline ranking evaluation (see CONTEXT.md)
```
