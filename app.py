"""
Second Router — OpenRouter-compatible video generation API.

Client-facing surface mirrors OpenRouter's video contract:
    POST   /api/v1/videos               -> submit a generation job
    GET    /api/v1/videos/{job_id}      -> poll job status / get result URLs
    GET    /api/v1/videos/{job_id}/content?index=0  -> 302 to the asset
    GET    /api/v1/videos/models        -> list available models

This module is the HTTP surface and knows nothing about any provider. Each call
is dispatched to a provider from `providers/`, chosen by the model slug on
submit and by the provider tag inside the job id on poll.

The service is STATELESS: the provider's task id is encoded inside the job id we
return, so there is no database and you can scale to zero / run N replicas.
"""

import base64
import json
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Imported after load_dotenv(): providers read their config from the environment
# at import time, so the .env has to be in place first.
import providers  # noqa: E402
from providers.base import UpstreamError  # noqa: E402

# ---------------------------------------------------------------------------
# Config (all from environment). Provider credentials live in the provider.
# ---------------------------------------------------------------------------
ROUTER_KEYS = {k.strip() for k in os.environ.get("ROUTER_KEYS", "").split(",") if k.strip()}
# Absolute URL clients use to reach THIS service (for polling_url). Blank -> derive
# from the request. In cloud, set this to your public https URL.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def require_key(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not ROUTER_KEYS or token not in ROUTER_KEYS:
        raise HTTPException(status_code=401, detail="invalid or missing router key")


def encode_job_id(provider: str, task_id: str) -> str:
    raw = json.dumps({"p": provider, "t": task_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_job_id(job_id: str) -> tuple[str, str]:
    try:
        pad = "=" * (-len(job_id) % 4)
        obj = json.loads(base64.urlsafe_b64decode(job_id + pad))
        return obj["p"], obj["t"]
    except Exception:
        raise HTTPException(status_code=404, detail="unknown job id")


def public_base(request: Request) -> str:
    return PUBLIC_BASE_URL or str(request.base_url).rstrip("/")


def _resolve(job_id: str):
    """job id -> (provider, task id), with config checked."""
    name, task_id = decode_job_id(job_id)
    provider = providers.for_name(name)
    provider.require_config()
    return provider, task_id


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Second Router (OpenRouter-compatible)")
client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "upstream": providers.upstream(),
        "models": providers.slugs(),
        "providers": sorted(providers.upstreams()),
    }


# NOTE: declare the static /models route BEFORE the dynamic /{job_id} route.
@app.get("/api/v1/videos/models")
async def list_video_models(request: Request):
    require_key(request)
    return {"data": providers.catalog()}


@app.post("/api/v1/videos")
async def create_video(request: Request):
    require_key(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    provider, model_id = providers.for_slug(body.get("model"))
    provider.require_config()
    try:
        task_id = await provider.submit(client, body, model_id)
    except UpstreamError as e:
        # Providers validate strictly; pass the message through so the caller
        # learns exactly which knob their model rejected.
        return JSONResponse(status_code=e.status_code, content={"error": e.payload})

    job_id = encode_job_id(provider.name, task_id)
    base = public_base(request)
    return JSONResponse(status_code=202, content={
        "id": job_id,
        "polling_url": f"{base}/api/v1/videos/{job_id}",
        "status": "pending",
    })


@app.get("/api/v1/videos/{job_id}")
async def get_video(job_id: str, request: Request):
    require_key(request)
    provider, task_id = _resolve(job_id)
    result = await provider.poll(client, task_id)

    status = result["status"]
    resp = {
        "id": job_id,
        "polling_url": f"{public_base(request)}/api/v1/videos/{job_id}",
        "status": status,
    }
    if status == "completed":
        urls = result["urls"]
        resp["unsigned_urls"] = urls
        resp["output"] = urls  # convenience alias
        if result.get("last_frame_url"):
            resp["last_frame_url"] = result["last_frame_url"]
    elif status == "failed":
        resp["error"] = result["error"]
    return JSONResponse(resp)


@app.get("/api/v1/videos/{job_id}/content")
async def get_content(job_id: str, request: Request, index: int = 0):
    require_key(request)
    provider, task_id = _resolve(job_id)
    result = await provider.poll(client, task_id)
    if result["status"] != "completed":
        raise HTTPException(status_code=409, detail="video not ready")

    urls = result["urls"]
    if index >= len(urls):
        raise HTTPException(status_code=404, detail="no content at that index")

    # Hand the client the presigned asset URL and stay out of the data path. The
    # store serves range requests natively, so seeking works, and neither our
    # bandwidth nor a pooled connection is spent on the transfer. This discloses
    # nothing new — the same URL is already in `unsigned_urls` on the poll
    # response — and no auth header of ours travels to the CDN.
    return RedirectResponse(urls[index], status_code=302)
