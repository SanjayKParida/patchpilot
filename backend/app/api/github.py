import os
from dotenv import load_dotenv
from fastapi import APIRouter

from app.services.github_service import GithubService

load_dotenv()

github_service = GithubService(os.getenv("GITHUB_TOKEN"))

github_router = APIRouter(tags=["github"])

@github_router.get("/issues")
def get_issues(owner: str, repo: str):
    return github_service.get_issues(owner, repo)
