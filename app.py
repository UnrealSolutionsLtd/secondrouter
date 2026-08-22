"""
video-router — OpenRouter-compatible video generation API, BytePlus backend.

Client-facing surface mirrors OpenRouter's video contract:
    POST   /api/v1/videos               -> submit a generation job
    GET    /api/v1/videos/{job_id}      -> poll job status / get result URLs
    GET    /api/v1/videos/{job_id}/content?index=0  -> stream the MP4
    GET    /api/v1/videos/models        -> list available models

Internally each call is translated to a BytePlus ModelArk create/retrieve task.
The service is STATELESS: the BytePlus task id is encoded inside the job id we
return, so there is no database and you can scale to zero / run N replicas.

The BytePlus mapping below is confirmed against the ModelArk "Video generation
API" reference (docs 1520757) and verified with live create/retrieve calls.
Two details are worth knowing before editing:

  * Generation knobs (resolution, ratio, duration, seed, ...) go TOP-LEVEL in
    the create-task body. ModelArk calls this the "conventional method" and
    validates it strictly. The legacy alternative — appending "--rs 720p" style
    flags to the prompt text — is only weakly validated (invalid flags are
    silently ignored), so we do not use it. A nested parameters={...} object is
    part of neither contract and is silently dropped by the API.
  * Per-model support for each knob varies. We forward what the client sends and
    let ModelArk's strict validation reject it, surfacing that error verbatim.
    That keeps BytePlus the single source of truth instead of duplicating its
    capability matrix here.
"""

import os
import json
import base64
import httpx
import yaml
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Config (all from environment)
# ---------------------------------------------------------------------------
# Regional base URLs: ap-southeast-1 serves every model; eu-west-1 serves only
# the seed-2-0 and seedream-5-0-lite families.
ARK_BASE_URL = os.environ.get(
    "ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3"
).rstrip("/")
ARK_API_KEY = os.environ.get("ARK_API_KEY")  # secret upstream BytePlus key
ROUTER_KEYS = {k.strip() for k in os.environ.get("ROUTER_KEYS", "").split(",") if k.strip()}
# Absolute URL clients use to reach THIS service (for polling_url). Blank -> derive
# from the request. In cloud, set this to your public https URL.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

ARK_CREATE_TASK_PATH = os.environ.get("ARK_CREATE_TASK_PATH", "/contents/generations/tasks")


def ark_retrieve_task_path(task_id: str) -> str:
    return f"{ARK_CREATE_TASK_PATH}/{task_id}"


# OpenRouter model slug -> BytePlus model id (from models.yaml).
MODEL_MAP: dict[str, str] = {}
try:
    with open("models.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
        for m in (cfg.get("models") or []):
            MODEL_MAP[m["openrouter"]] = m["byteplus"]
except FileNotFoundError:
    pass

# BytePlus task status -> OpenRouter status enum. These five are the complete
# documented set. An unrecognized value is treated as an error rather than
# silently mapped, so a schema change surfaces instead of polling forever.
STATUS_MAP = {
    "queued": "pending",
    "running": "processing",
    "succeeded": "completed",
    "failed": "failed",
    "expired": "expired",
}

# Client-facing knob -> BytePlus top-level field. Left side accepts a couple of
# OpenRouter aliases; right side is the ModelArk field name.
PARAM_ALIASES = {
    "duration": "duration",
    "seconds": "duration",
    "frames": "frames",
    "resolution": "resolution",
    "size": "resolution",
    "aspect_ratio": "ratio",
    "ratio": "ratio",
    "seed": "seed",
    "generate_audio": "generate_audio",
    "watermark": "watermark",
    "camera_fixed": "camera_fixed",
    "output_format": "output_format",
    "return_last_frame": "return_last_frame",
    "omni_reference_task_type": "omni_reference_task_type",
    "service_tier": "service_tier",
    "execution_expires_after": "execution_expires_after",
    "priority": "priority",
    "safety_identifier": "safety_identifier",
    "draft": "draft",
}

# content[].role values, per the spec. Frame roles and reference roles are
# mutually exclusive scenarios and cannot be mixed in one task.
FRAME_ROLES = {
    "first": "first_frame", "first_frame": "first_frame",
    "last": "last_frame", "last_frame": "last_frame",
}
REFERENCE_ROLES = {
    "image": ("image_url", "reference_image"),
    "video": ("video_url", "reference_video"),
    "audio": ("audio_url", "reference_audio"),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def require_key(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not ROUTER_KEYS or token not in ROUTER_KEYS:
        raise HTTPException(status_code=401, detail="invalid or missing router key")


def require_config() -> None:
    if not ARK_API_KEY:
        raise HTTPException(status_code=500, detail="ARK_API_KEY not configured")


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


def ark_headers() -> dict:
    return {"Authorization": f"Bearer {ARK_API_KEY}", "Content-Type": "application/json"}


def _safe_json(r: httpx.Response):
    try:
        return r.json()
    except Exception:
        return {"message": r.text[:500]}


def _asset_item(kind: str, url: str, role: str | None) -> dict:
    """Build one content[] entry. `kind` is image_url / video_url / audio_url."""
    item: dict = {"type": kind, kind: {"url": url}}
    if role:
        item["role"] = role
    return item


def _asset_url(obj) -> str | None:
    """Accept a bare URL string or an object carrying one under a few key names.
    A URL may be an https URL, a data: base64 payload, or an asset://<id> URI."""
    if isinstance(obj, str):
        return obj or None
    if isinstance(obj, dict):
        for k in ("url", "image_url", "video_url", "audio_url"):
            v = obj.get(k)
            if isinstance(v, dict):
                v = v.get("url")
            if isinstance(v, str) and v:
                return v
    return None


def translate_request(body: dict) -> dict:
    """Map an OpenRouter /api/v1/videos request onto a BytePlus create-task body.

    OpenRouter (client-facing) fields:
      model, prompt, duration|seconds, resolution|size, aspect_ratio, seed,
      generate_audio, watermark, camera_fixed, output_format, frames,
      frame_images[], input_references[], provider (passthrough)

    `callback_url` is accepted and deliberately ignored — see invariant 4 in
    CLAUDE.md. ModelArk does support it natively, but forwarding it would emit
    BytePlus-shaped payloads to the client instead of OpenRouter events.
    """
    slug = body.get("model")
    if not slug or slug not in MODEL_MAP:
        raise HTTPException(status_code=404, detail=f"no endpoints found for model '{slug}'")

    content: list[dict] = []
    prompt = body.get("prompt", "")
    if prompt:
        content.append({"type": "text", "text": prompt})

    # image-to-video: first / last frame. Role may be omitted for a lone first
    # frame, but we always set it explicitly.
    frames_seen = 0
    for fi in (body.get("frame_images") or []):
        url = _asset_url(fi)
        if not url:
            continue
        raw_role = (fi.get("frame_type") if isinstance(fi, dict) else None) or "first_frame"
        role = FRAME_ROLES.get(str(raw_role).lower())
        if not role:
            raise HTTPException(
                status_code=400,
                detail=f"invalid frame_type '{raw_role}' (expected first_frame or last_frame)",
            )
        content.append(_asset_item("image_url", url, role))
        frames_seen += 1

    # omni reference-to-video: reference images / videos / audio.
    refs_seen = 0
    for ref in (body.get("input_references") or []):
        url = _asset_url(ref)
        if not url:
            continue
        kind = (ref.get("type") if isinstance(ref, dict) else None) or "image"
        mapped = REFERENCE_ROLES.get(str(kind).lower())
        if not mapped:
            raise HTTPException(
                status_code=400,
                detail=f"invalid input_reference type '{kind}' (expected image, video or audio)",
            )
        content.append(_asset_item(mapped[0], url, mapped[1]))
        refs_seen += 1

    # The spec makes these mutually exclusive scenarios; catching it here gives a
    # clearer error than the upstream one.
    if frames_seen and refs_seen:
        raise HTTPException(
            status_code=400,
            detail="frame_images and input_references cannot be combined — "
                   "first/last-frame and omni reference-to-video are separate task types",
        )
    if not content:
        raise HTTPException(
            status_code=400, detail="provide a prompt, frame_images or input_references"
        )

    bp_body: dict = {"model": MODEL_MAP[slug], "content": content}

    # Generation knobs go top-level. First alias present wins, so an explicit
    # `duration` beats `seconds` and `resolution` beats `size`.
    for client_field, ark_field in PARAM_ALIASES.items():
        if body.get(client_field) is not None and ark_field not in bp_body:
            bp_body[ark_field] = body[client_field]

    # escape hatch: let callers pass raw BytePlus fields through untouched
    prov = body.get("provider")
    if isinstance(prov, dict) and isinstance(prov.get("byteplus_extra"), dict):
        bp_body.update(prov["byteplus_extra"])

    return bp_body


def extract_task_id(create_response: dict):
    """Create-task returns exactly {"id": "cgt-..."}."""
    return create_response.get("id")


def extract_status(bp: dict) -> str:
    raw = str(bp.get("status") or "").lower()
    status = STATUS_MAP.get(raw)
    if status is None:
        raise HTTPException(
            status_code=502, detail=f"unrecognized upstream task status '{bp.get('status')}'"
        )
    return status


def extract_error(bp: dict):
    err = bp.get("error")
    if isinstance(err, dict):
        code, message = err.get("code"), err.get("message")
        if code and message:
            return f"{code}: {message}"
        return message or code or json.dumps(err)
    return err


def extract_result_urls(bp: dict) -> list[str]:
    """A finished task carries its video at content.video_url (a single string)."""
    url = (bp.get("content") or {}).get("video_url")
    return [url] if isinstance(url, str) and url else []


def extract_last_frame_url(bp: dict):
    """Present only when the task was created with return_last_frame: true."""
    return (bp.get("content") or {}).get("last_frame_url")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="video-router (OpenRouter-compatible, BytePlus backend)")
client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))


async def retrieve_task(task_id: str) -> dict:
    r = await client.get(f"{ARK_BASE_URL}{ark_retrieve_task_path(task_id)}", headers=ark_headers())
    if r.status_code >= 400:
        raise HTTPException(status_code=r.status_code, detail=_safe_json(r))
    return r.json()


@app.get("/healthz")
async def healthz():
    return {"ok": True, "upstream": ARK_BASE_URL, "models": sorted(MODEL_MAP.keys())}


# NOTE: declare the static /models route BEFORE the dynamic /{job_id} route.
@app.get("/api/v1/videos/models")
async def list_video_models(request: Request):
    require_key(request)
    return {"data": [{"id": slug, "backend": bp} for slug, bp in MODEL_MAP.items()]}


@app.post("/api/v1/videos")
async def create_video(request: Request):
    require_key(request)
    require_config()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    bp_body = translate_request(body)
    r = await client.post(
        f"{ARK_BASE_URL}{ARK_CREATE_TASK_PATH}", headers=ark_headers(), json=bp_body
    )
    if r.status_code >= 400:
        # ModelArk validates strictly; pass its message through so the caller
        # learns exactly which knob their model rejected.
        payload = _safe_json(r)
        return JSONResponse(
            status_code=r.status_code, content={"error": payload.get("error", payload)}
        )

    task_id = extract_task_id(r.json())
    if not task_id:
        raise HTTPException(status_code=502, detail="BytePlus did not return a task id")

    job_id = encode_job_id("byteplus", task_id)
    base = public_base(request)
    return JSONResponse(status_code=202, content={
        "id": job_id,
        "polling_url": f"{base}/api/v1/videos/{job_id}",
        "status": "pending",
    })


@app.get("/api/v1/videos/{job_id}")
async def get_video(job_id: str, request: Request):
    require_key(request)
    require_config()
    _, task_id = decode_job_id(job_id)
    bp = await retrieve_task(task_id)

    status = extract_status(bp)
    resp = {
        "id": job_id,
        "polling_url": f"{public_base(request)}/api/v1/videos/{job_id}",
        "status": status,
    }
    if status == "completed":
        urls = extract_result_urls(bp)
        resp["unsigned_urls"] = urls
        resp["output"] = urls  # convenience alias
        last_frame = extract_last_frame_url(bp)
        if last_frame:
            resp["last_frame_url"] = last_frame
    elif status == "failed":
        resp["error"] = extract_error(bp)
    return JSONResponse(resp)


@app.get("/api/v1/videos/{job_id}/content")
async def get_content(job_id: str, request: Request, index: int = 0):
    require_key(request)
    require_config()
    _, task_id = decode_job_id(job_id)
    bp = await retrieve_task(task_id)
    if extract_status(bp) != "completed":
        raise HTTPException(status_code=409, detail="video not ready")

    urls = extract_result_urls(bp)
    if index >= len(urls):
        raise HTTPException(status_code=404, detail="no content at that index")

    # Stream the bytes through. No auth header is sent to the asset URL (it's a
    # presigned TOS URL, valid 24h) so the upstream key is never leaked to a CDN.
    upstream = await client.send(client.build_request("GET", urls[index]), stream=True)
    headers = {"Content-Type": upstream.headers.get("content-type", "video/mp4")}
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=headers,
        background=BackgroundTask(upstream.aclose),
    )
