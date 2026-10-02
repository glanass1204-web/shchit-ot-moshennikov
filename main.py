from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from analyzer import MAX_LEN, analyze

BASE = Path(__file__).parent

app = FastAPI(title="Щит от мошенников", version="1.0.0")


class CheckRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_LEN)


@app.post("/api/analyze")
def api_analyze(req: CheckRequest) -> dict:
    return analyze(req.text)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE / "index.html")


@app.get("/static/style.css", include_in_schema=False)
def css() -> FileResponse:
    return FileResponse(BASE / "style.css", media_type="text/css")


@app.get("/static/app.js", include_in_schema=False)
def js() -> FileResponse:
    return FileResponse(BASE / "app.js", media_type="application/javascript")
