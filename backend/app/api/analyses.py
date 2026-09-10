import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.dependencies import (
    get_analysis_runner,
    get_analysis_store,
    get_github_service,
    get_llm_service,
    get_optional_session,
    get_patch_delivery_service,
    get_patch_generator,
    get_patch_validator,
    get_repository_access,
    get_repository_snapshot_store,
    get_visible_analysis,
)
from app.errors import (
    IssueNotFound,
    PatchGenerationInProgress,
    PatchPilotError,
    UpstreamUnavailable,
)
from app.application.patch_delivery_service import PatchDeliveryService
from app.services.analysis_runner import AnalysisRunner
from app.services.issue_followup_service import IssueFollowUpService
from app.schemas import (
    Analysis,
    AnalysisRequest,
    Answer,
    ContextPackage,
    FileSource,
    PatchApproval,
    PatchDelivery,
    PatchProposal,
    PatchValidation,
    QuestionRequest,
)
from app.services.patch_validation_types import ValidationConfig
from app.services.validation_profiles import select_validation_inspection

logger = logging.getLogger(__name__)

analyses_router = APIRouter(tags=["analyses"])


def run_analysis(analysis_id, request, runner, store):
    """
    Execute one analysis outside the request cycle.

    Any failure is recorded on the job rather than raised: nobody is
    listening on this call stack, and the client learns about it by
    polling.
    """

    def on_stage(stage):
        store.mark_running(analysis_id, stage)

    try:
        record = store.get(analysis_id)
        result = runner.run(
            request.owner,
            request.repo,
            request.issue_number,
            on_stage=on_stage,
            ref=record.get("commit_sha") or record.get("ref"),
        )
        store.mark_completed(analysis_id, result)

    except PatchPilotError as e:
        store.mark_failed(analysis_id, str(e))

    except Exception as e:
        logger.exception("Analysis %s failed", analysis_id)
        store.mark_failed(
            analysis_id,
            f"Unexpected error during analysis: {e}",
        )


@analyses_router.post(
    "",
    response_model=Analysis,
    status_code=202,
)
def create_analysis(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    runner=Depends(get_analysis_runner),
    store=Depends(get_analysis_store),
    github=Depends(get_github_service),
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
):
    """
    Start analysing an issue.

    Returns immediately with a job to poll. A full analysis clones the
    repository's source and calls a language model, which is far
    longer than a request should be held open for.

    An explicit `ref`/`commit` is resolved to a SHA before the job is
    created. An invalid ref fails this request; it is never replaced
    with HEAD.

    A completed or in-flight analysis for the same issue is returned
    instead of starting another run. Pass `force` to diagnose again.
    """

    access.assert_can_analyze(request.owner, request.repo, session)

    requested_ref = request.effective_ref()
    commit_sha = None

    github_for_job = github
    runner_for_job = runner
    if access.app_configured:
        github_for_job = access.github_service_for(
            request.owner,
            request.repo,
            session,
            write=False,
        )
        runner_for_job = AnalysisRunner(
            github_service=github_for_job,
            llm_service=get_llm_service(),
            context_builder=runner.context_builder,
            snapshot_store=get_repository_snapshot_store(),
        )

    if requested_ref is not None:
        commit_sha = github_for_job.resolve_commit(
            request.owner,
            request.repo,
            requested_ref,
        )

    user_id = session.user_id if session else None
    if not request.force:
        existing = store.find_reusable(
            request.owner,
            request.repo,
            request.issue_number,
            commit_sha=commit_sha,
            ref=requested_ref,
            user_id=user_id,
        )
        if existing is not None:
            return existing

    granted = None
    if session is not None:
        granted = access.store.find_repository(
            session.user_id,
            request.owner,
            request.repo,
        )

    record = store.create(
        request.owner,
        request.repo,
        request.issue_number,
        ref=requested_ref,
        commit_sha=commit_sha,
        user_id=user_id,
        github_repo_id=granted.github_repo_id if granted else None,
    )

    background_tasks.add_task(
        run_analysis,
        record["id"],
        request,
        runner_for_job,
        store,
    )

    return record


@analyses_router.get("/{analysis_id}", response_model=Analysis)
def get_analysis(record=Depends(get_visible_analysis)):
    return record


@analyses_router.get(
    "/{analysis_id}/context",
    response_model=ContextPackage,
)
def get_analysis_context(
    record=Depends(get_visible_analysis),
):
    """
    Bounded context for a completed analysis.

    Slice content is kept off the polling Analysis payload and served
    here instead, for the same reason ranked-file source is served from
    GET /files.
    """

    if record.get("status") != "completed":
        raise IssueNotFound(
            "This analysis has not completed yet"
        )

    package = record.get("context_package")

    if package is None:
        message = record.get("context_error") or (
            "No context package is available for this analysis"
        )
        raise UpstreamUnavailable(message)

    return package


@analyses_router.post(
    "/{analysis_id}/patch",
    response_model=PatchProposal,
)
def create_analysis_patch(
    analysis_id: str,
    record=Depends(get_visible_analysis),
    store=Depends(get_analysis_store),
    patch_generator=Depends(get_patch_generator),
    llm=Depends(get_llm_service),
):
    """
    Generate a structured patch proposal from stored context.

    Uses only the analysis issue, diagnosis, and ContextPackage.
    Does not search the repository or fetch files from GitHub.
    A previously stored proposal is returned without regenerating.
    """

    started = time.monotonic()
    logger.info("patch_request_start analysis_id=%s", analysis_id)

    def elapsed_ms():
        return int((time.monotonic() - started) * 1000)

    if record.get("status") != "completed":
        raise IssueNotFound(
            "This analysis has not completed yet"
        )

    if record.get("diagnosis") is None:
        message = record.get("diagnosis_error") or (
            "No diagnosis is available for this analysis"
        )
        logger.info(
            "patch_http_response elapsed_ms=%s status=502",
            elapsed_ms(),
        )
        raise UpstreamUnavailable(message)

    package = record.get("context_package")

    if package is None:
        message = record.get("context_error") or (
            "No context package is available for this analysis"
        )
        logger.info(
            "patch_http_response elapsed_ms=%s status=502",
            elapsed_ms(),
        )
        raise UpstreamUnavailable(message)

    if llm is None:
        logger.info(
            "patch_http_response elapsed_ms=%s status=502",
            elapsed_ms(),
        )
        raise UpstreamUnavailable(
            "No language model is configured"
        )

    kind, existing = store.begin_patch_generation(analysis_id)

    if kind == "cached":
        logger.info(
            "patch_http_response elapsed_ms=%s status=200 cache=hit",
            elapsed_ms(),
        )
        return existing

    if kind == "running":
        logger.info(
            "patch_http_response elapsed_ms=%s status=409",
            elapsed_ms(),
        )
        raise PatchGenerationInProgress(
            "Patch generation is already running for this analysis"
        )

    payload = None
    error = None
    try:
        proposal = patch_generator.generate(
            record.get("issue") or {},
            record["diagnosis"],
            package,
        )
        payload = proposal.to_dict()
        store.finish_patch_generation(
            analysis_id,
            proposal=payload,
        )
        logger.info(
            "patch_http_response elapsed_ms=%s status=200",
            elapsed_ms(),
        )
        return payload
    except Exception as e:
        error = str(e)
        store.finish_patch_generation(
            analysis_id,
            error=error,
        )
        logger.info(
            "patch_http_response elapsed_ms=%s status=502",
            elapsed_ms(),
        )
        raise UpstreamUnavailable(
            f"Patch generation failed: {e}"
        ) from e
    except BaseException:
        store.finish_patch_generation(
            analysis_id,
            proposal=payload,
            error=error,
        )
        raise


@analyses_router.get(
    "/{analysis_id}/patch",
    response_model=PatchProposal,
)
def get_analysis_patch(
    record=Depends(get_visible_analysis),
):
    """
    Return a previously generated patch proposal.

    Does not call the model. Use POST /patch to generate one.
    """

    if record.get("status") != "completed":
        raise IssueNotFound(
            "This analysis has not completed yet"
        )

    proposal = record.get("patch_proposal")

    if proposal is not None:
        return proposal

    if record.get("patch_generating"):
        raise PatchGenerationInProgress(
            "Patch generation is already running for this analysis"
        )

    message = record.get("patch_error") or (
        "No patch proposal is available for this analysis"
    )
    raise UpstreamUnavailable(message)


def _validation_files(record):
    """
    File map PatchValidator applies against.

    Prefer the full pinned snapshot. Ranked `sources` stay the UI
    view and are only a fallback for jobs that never stored one.
    A snapshot from a different commit is refused rather than mixed.
    """

    snapshot = record.get("snapshot")
    commit_sha = record.get("commit_sha")
    snapshot_commit = record.get("snapshot_commit")

    if snapshot is not None:
        if (
            commit_sha
            and snapshot_commit
            and snapshot_commit != commit_sha
        ):
            raise UpstreamUnavailable(
                "The stored repository snapshot does not match the "
                "analysis commit. Validation was not started."
            )
        return snapshot

    return record.get("sources") or {}


def _validation_payload(result, inspection):
    """
    Validator dict plus profile metadata for the review UI.

    A passed apply with no commands is not toolchain success — the
    client uses `runnable` to show unavailable instead of passed.
    """

    payload = result.to_dict()
    payload["runnable"] = inspection.runnable
    payload["unavailable_reason"] = (
        inspection.reason if not inspection.runnable else ""
    )
    return payload


@analyses_router.post(
    "/{analysis_id}/patch/validate",
    response_model=PatchValidation,
)
def validate_analysis_patch(
    analysis_id: str,
    record=Depends(get_visible_analysis),
    store=Depends(get_analysis_store),
    validator=Depends(get_patch_validator),
):
    """
    Apply the stored proposal and run the matching validation profile.

    Uses the full pinned repository snapshot stored on the job, not
    ranked `sources`. Does not call the model, search GitHub, or
    create a branch/PR. A previously stored result is returned
    without re-running.
    """

    if record.get("status") != "completed":
        raise IssueNotFound(
            "This analysis has not completed yet"
        )

    existing = record.get("patch_validation")

    if existing is not None:
        return existing

    proposal = record.get("patch_proposal")

    if proposal is None:
        message = record.get("patch_error") or (
            "No patch proposal is available for this analysis"
        )
        raise UpstreamUnavailable(message)

    files = _validation_files(record)
    inspection = select_validation_inspection(files, proposal=proposal)
    config = ValidationConfig(commands=list(inspection.commands))

    try:
        result = validator.validate(proposal, files, config)
    except Exception as e:
        store.update(
            analysis_id,
            patch_validation_error=str(e),
        )
        raise UpstreamUnavailable(
            f"Patch validation failed: {e}"
        ) from e

    payload = _validation_payload(result, inspection)

    store.update(
        analysis_id,
        patch_validation=payload,
        patch_validation_error=None,
    )

    return payload


@analyses_router.get(
    "/{analysis_id}/patch/validate",
    response_model=PatchValidation,
)
def get_analysis_patch_validation(
    record=Depends(get_visible_analysis),
):
    """
    Return a previously stored validation result.

    Does not apply the patch or run commands. Use POST to validate.
    """

    if record.get("status") != "completed":
        raise IssueNotFound(
            "This analysis has not completed yet"
        )

    result = record.get("patch_validation")

    if result is None:
        message = record.get("patch_validation_error") or (
            "No patch validation is available for this analysis"
        )
        raise UpstreamUnavailable(message)

    return result


@analyses_router.post(
    "/{analysis_id}/patch/approve",
    response_model=PatchApproval,
)
def approve_analysis_patch(
    analysis_id: str,
    record=Depends(get_visible_analysis),
    delivery=Depends(get_patch_delivery_service),
    session=Depends(get_optional_session),
):
    """
    Record explicit approval of the stored validated proposal.

    Does not take a patch body. Owner, repo, commit, and files come
    from the analysis record. Does not create a branch or PR.
    """

    return delivery.approve(analysis_id, actor=session).to_dict()


@analyses_router.get(
    "/{analysis_id}/patch/approve",
    response_model=PatchApproval,
)
def get_analysis_patch_approval(
    analysis_id: str,
    record=Depends(get_visible_analysis),
    delivery=Depends(get_patch_delivery_service),
):
    """Return a previously recorded approval. Does not approve."""

    return delivery.get_approval(analysis_id).to_dict()


@analyses_router.post(
    "/{analysis_id}/patch/deliver",
    response_model=PatchDelivery,
)
def deliver_analysis_patch(
    analysis_id: str,
    record=Depends(get_visible_analysis),
    delivery=Depends(get_patch_delivery_service),
    access=Depends(get_repository_access),
    session=Depends(get_optional_session),
    store=Depends(get_analysis_store),
):
    """
    Open a draft PR from the stored approved proposal.

    Branches from the analyzed commit SHA, applies the stored
    proposal, and never updates the default branch. Request bodies
    are ignored: there is no client-supplied patch or repository.
    """

    access.assert_can_deliver(record, session)

    service = delivery
    if access.app_configured:
        owner, repo = record["repository"]["owner"], record["repository"]["repo"]
        service = PatchDeliveryService(
            store,
            access.github_service_for(owner, repo, session, write=True),
            access.github_writer_for(owner, repo, session),
            access=access,
        )

    return service.deliver(analysis_id, actor=session).to_dict()


@analyses_router.get(
    "/{analysis_id}/patch/deliver",
    response_model=PatchDelivery,
)
def get_analysis_patch_delivery(
    analysis_id: str,
    record=Depends(get_visible_analysis),
    delivery=Depends(get_patch_delivery_service),
):
    """Return the latest delivery attempt. Does not create a PR."""

    return delivery.get_delivery(analysis_id).to_dict()


def _context_package_paths(package):
    """Paths the ContextPackage already admitted (slices + file rollup)."""

    if not isinstance(package, dict):
        return set()

    paths = set()

    for entry in package.get("slices") or []:
        if isinstance(entry, dict):
            path = entry.get("path")
            if path:
                paths.add(path)

    for entry in package.get("files") or []:
        if isinstance(entry, dict):
            path = entry.get("path")
            if path:
                paths.add(path)

    return paths


def _analysis_file_content(record, path):
    """
    Resolve source for one client-openable analysis file.

    Ranked `sources` cover Diagnosis navigation. ContextPackage can
    also admit supporting files outside the ranked top-N; those are
    served from the pinned snapshot only when the package already
    includes them — never arbitrary repository paths.
    """

    sources = record.get("sources") or {}
    if path in sources:
        return sources[path]

    if path not in _context_package_paths(record.get("context_package")):
        return None

    snapshot = record.get("snapshot") or {}
    if path in snapshot:
        return snapshot[path]

    return None


@analyses_router.get(
    "/{analysis_id}/files",
    response_model=FileSource,
)
def get_analysis_file(
    path: str = Query(..., description="Repository path of the file"),
    record=Depends(get_visible_analysis),
):
    """
    Source of one file from a completed analysis.

    Served per file rather than inside the analysis payload: the poll
    response is fetched repeatedly while an analysis runs, and a
    repository's source has no business being in it.

    Openable paths are the analysis ranked sources, plus any file the
    stored ContextPackage already admitted. Arbitrary repository paths
    remain unavailable.
    """

    content = _analysis_file_content(record, path)

    if content is None:
        raise IssueNotFound(
            f"{path} is not among the files this analysis ranked"
        )

    return FileSource(
        path=path,
        content=content,
        lines=len(content.splitlines()),
    )


@analyses_router.post(
    "/{analysis_id}/questions",
    response_model=Answer,
)
def ask_question(
    request: QuestionRequest,
    record=Depends(get_visible_analysis),
    llm=Depends(get_llm_service),
):
    """
    Answer one question about a completed analysis.

    Stateless by design — see IssueFollowUpService. The question is
    answered against the analysis's own evidence, never against a
    conversation history.
    """

    if record.get("status") != "completed":
        raise IssueNotFound(
            "This analysis has not completed yet"
        )

    if llm is None:
        raise UpstreamUnavailable(
            "No language model is configured"
        )

    try:
        answer = IssueFollowUpService(llm_service=llm).answer(
            request.question,
            record,
            record.get("sources") or {},
        )
    except ValueError as e:
        raise UpstreamUnavailable(str(e)) from e

    return Answer(question=request.question.strip(), answer=answer)
