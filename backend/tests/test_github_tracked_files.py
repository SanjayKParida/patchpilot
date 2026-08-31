"""
Tracked-file snapshot policy: UTF-8 blobs under a size cap.

No language include-list. pubspec.yaml is kept for the same reason
README.md is — it is a tracked text file — not because it is Flutter.
"""

from app.services.github_service import (
    MAX_TRACKED_BLOB_BYTES,
    GithubService,
    decode_utf8_or_none,
    tracked_blob_over_size,
)


def test_utf8_text_decodes():
    assert decode_utf8_or_none(b"name: app\n") == "name: app\n"


def test_binary_bytes_are_skipped():
    assert decode_utf8_or_none(b"\xff\xfe\x00\x00") is None


def test_size_cap_skips_oversized_blobs():
    assert tracked_blob_over_size({"size": MAX_TRACKED_BLOB_BYTES + 1})
    assert not tracked_blob_over_size({"size": 100})
    assert not tracked_blob_over_size({})


class _FakeGithub(GithubService):
    def __init__(self, blobs):
        super().__init__("token")
        self._blobs = blobs

    def get_repository_tree(self, owner, repo, ref=None):
        return [
            {
                "path": path,
                "sha": sha,
                "type": "blob",
                "size": len(raw),
            }
            for path, (sha, raw) in self._blobs.items()
        ]

    def get_blob_bytes(self, owner, repo, sha):
        for _path, (blob_sha, raw) in self._blobs.items():
            if blob_sha == sha:
                return raw
        raise AssertionError(f"unknown blob {sha}")


def test_tracked_files_keep_yaml_and_extensionless_text():
    github = _FakeGithub({
        "pubspec.yaml": ("sha-yaml", b"name: demo\n"),
        "LICENSE": ("sha-lic", b"MIT\n"),
        "lib/main.dart": ("sha-dart", b"void main() {}\n"),
        "logo.png": ("sha-png", b"\x89PNG\r\n\x1a\n"),
        "huge.bin": ("sha-huge", b"x" * (MAX_TRACKED_BLOB_BYTES + 8)),
    })

    files = github.get_repository_tracked_files("o", "r")
    paths = {item["path"] for item in files}

    assert paths == {"pubspec.yaml", "LICENSE", "lib/main.dart"}
    assert "logo.png" not in paths
    assert "huge.bin" not in paths


def test_source_files_still_filter_by_language_extension():
    github = _FakeGithub({
        "pubspec.yaml": ("sha-yaml", b"name: demo\n"),
        "lib/main.dart": ("sha-dart", b"void main() {}\n"),
    })

    files = github.get_repository_source_files("o", "r")
    paths = {item["path"] for item in files}

    assert paths == {"lib/main.dart"}
