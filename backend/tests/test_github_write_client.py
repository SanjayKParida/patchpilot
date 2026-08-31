"""GithubWriteClient maps GitHub HTTP statuses. No live network."""

import httpx
import pytest

from app.errors import (
    GitRefConflict,
    GithubPermissionDenied,
    RepositoryNotFound,
    UpstreamUnavailable,
)
from app.infrastructure.github_write_client import GithubWriteClient


def _client(handler):
    transport = httpx.MockTransport(handler)
    return GithubWriteClient(
        "token",
        client=httpx.Client(transport=transport),
    )


def test_create_blob_returns_sha():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path.endswith("/git/blobs")
        return httpx.Response(201, json={"sha": "blobsha"})

    writer = _client(handler)
    assert writer.create_blob("o", "r", "hello") == "blobsha"


def test_401_is_permission_denied():
    def handler(request):
        return httpx.Response(401, text="bad credentials")

    writer = _client(handler)
    with pytest.raises(GithubPermissionDenied):
        writer.create_blob("o", "r", "x")


def test_403_is_permission_denied():
    def handler(request):
        return httpx.Response(403, text="resource not accessible")

    writer = _client(handler)
    with pytest.raises(GithubPermissionDenied):
        writer.create_ref("o", "r", "refs/heads/feature", "abc")


def test_repo_404_is_repository_not_found():
    def handler(request):
        return httpx.Response(404, text="not found")

    writer = _client(handler)
    with pytest.raises(RepositoryNotFound):
        writer.create_blob("o", "missing", "x")


def test_get_ref_404_is_missing_not_an_error():
    def handler(request):
        return httpx.Response(404, text="not found")

    writer = _client(handler)
    assert writer.get_ref("o", "r", "refs/heads/missing") is None


def test_create_ref_422_already_exists_is_conflict():
    def handler(request):
        return httpx.Response(
            422,
            text='{"message":"Reference already exists"}',
        )

    writer = _client(handler)
    with pytest.raises(GitRefConflict):
        writer.create_ref("o", "r", "refs/heads/taken", "abc")


def test_refuses_non_heads_ref():
    def handler(request):
        raise AssertionError("must not call GitHub")

    writer = _client(handler)
    with pytest.raises(UpstreamUnavailable):
        writer.create_ref("o", "r", "refs/tags/v1", "abc")


def test_500_is_upstream_unavailable():
    def handler(request):
        return httpx.Response(500, text="boom")

    writer = _client(handler)
    with pytest.raises(UpstreamUnavailable):
        writer.create_commit("o", "r", "msg", "tree", ["parent"])
