from fastapi import FastAPI
from app.api.github import github_router

app = FastAPI(title="PatchPilot API")

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(github_router, prefix="/github")