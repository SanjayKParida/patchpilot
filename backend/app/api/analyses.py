import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.dependencies import (
    get_analysis_runner,
    get_analysis_store,
    get_llm_service,
)
from app.errors import (
    IssueNotFound,
    PatchPilotError,
    UpstreamUnavailable,
)
from app.services.issue_followup_service import IssueFollowUpService
from app.schemas import (
    Analysis,
    AnalysisRequest,
    Answer,
    FileSource,
    QuestionRequest,
)

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
        result = runner.run(
            request.owner,
            request.repo,
            request.issue_number,
            on_stage=on_stage,
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
):
    """
    Start analysing an issue.

    Returns immediately with a job to poll. A full analysis clones the
    repository's source and calls a language model, which is far
    longer than a request should be held open for.
    """

    record = store.create(
        request.owner,
        request.repo,
        request.issue_number,
    )

    background_tasks.add_task(
        run_analysis,
        record["id"],
        request,
        runner,
        store,
    )

    return record


@analyses_router.get("/{analysis_id}", response_model=Analysis)
def get_analysis(
    analysis_id: str,
    store=Depends(get_analysis_store),
):
    return store.get(analysis_id)


@analyses_router.get(
    "/{analysis_id}/files",
    response_model=FileSource,
)
def get_analysis_file(
    analysis_id: str,
    path: str = Query(..., description="Repository path of the file"),
    store=Depends(get_analysis_store),
):
    """
    Source of one file from a completed analysis.

    Served per file rather than inside the analysis payload: the poll
    response is fetched repeatedly while an analysis runs, and a
    repository's source has no business being in it.

    Only files the analysis actually ranked are available, so this
    cannot be used to read arbitrary paths from the repository.
    """

    record = store.get(analysis_id)
    sources = record.get("sources") or {}

    if path not in sources:
        raise IssueNotFound(
            f"{path} is not among the files this analysis ranked"
        )

    content = sources[path]

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
    analysis_id: str,
    request: QuestionRequest,
    store=Depends(get_analysis_store),
    llm=Depends(get_llm_service),
):
    """
    Answer one question about a completed analysis.

    Stateless by design — see IssueFollowUpService. The question is
    answered against the analysis's own evidence, never against a
    conversation history.
    """

    record = store.get(analysis_id)

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
