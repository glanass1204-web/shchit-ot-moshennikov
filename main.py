from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from analyzer import MAX_LEN, analyze
from ai_analyzer import analyze_ai
import vk_bot

BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    vk_bot.check_token()
    yield


app = FastAPI(title="Антимошенник", version="1.1.0", lifespan=lifespan)
app.include_router(vk_bot.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


class CheckRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_LEN)
    use_ai: bool = False


@app.post("/api/analyze")
def api_analyze(req: CheckRequest) -> dict:
    result = analyze(req.text)
    if req.use_ai:
        result["ai"] = analyze_ai(req.text)
    return result


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": "antimoshennik", "version": "1.1.0", "vk": vk_bot.token_status}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/static/style.css", include_in_schema=False)
def css() -> FileResponse:
    return FileResponse(BASE / "style.css", media_type="text/css", headers={"Cache-Control": "no-cache"})


@app.get("/static/app.js", include_in_schema=False)
def js() -> FileResponse:
    return FileResponse(BASE / "app.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> FileResponse:
    return FileResponse(BASE / "manifest.webmanifest", media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(BASE / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/static/icon.svg", include_in_schema=False)
def app_icon() -> FileResponse:
    return FileResponse(BASE / "icon.svg", media_type="image/svg+xml")
