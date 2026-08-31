"""Infrastructure adapters for new delivery work.

Read-only GitHub access stays in `app.services.github_service`.
Writes go through `GithubWriteClient` only.
"""
