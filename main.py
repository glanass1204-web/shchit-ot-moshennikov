"""«Щит от мошенников» — веб-приложение на FastAPI.

Запуск:  uvicorn main:app --reload
Затем откройте http://127.0.0.1:8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from analyzer import MAX_LEN, analyze

BASE = Path(__file__).parent
STATIC = BASE / "static"

app = FastAPI(
    title="Щит от мошенников",
    description="Проверка подозрительных сообщений и ссылок на признаки мошенничества",
    version="1.0.0",
)


class CheckRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_LEN, description="Текст сообщения или ссылка")


@app.post("/api/analyze")
def api_analyze(req: CheckRequest) -> dict:
    # Текст не сохраняется и не логируется — анализ выполняется в памяти.
    return analyze(req.text)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
