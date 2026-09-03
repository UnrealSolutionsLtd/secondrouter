"""BytePlus ModelArk provider — everything provider-specific lives here.

The mapping is confirmed against the ModelArk "Video generation API" reference
(docs 1520757) and verified with live create/retrieve calls. Two details are
worth knowing before editing:

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

import json
import os

import httpx
from fastapi import HTTPException

from .base import UpstreamError

# ---------------------------------------------------------------------------
# Config (all from environment)
# ---------------------------------------------------------------------------
# Regional base URLs: ap-southeast-1 serves every model; eu-west-1 serves only
# the seed-2-0 and seedream-5-0-lite families.
ARK_BASE_URL = os.environ.get(
    "ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3"
).rstrip("/")
ARK_API_KEY = os.environ.get("ARK_API_KEY")  # secret upstream BytePlus key

ARK_CREATE_TASK_PATH = os.environ.get("ARK_CREATE_TASK_PATH", "/contents/generations/tasks")


def ark_retrieve_task_path(task_id: str) -> str:
    return f"{ARK_CREATE_TASK_PATH}/{task_id}"


def ark_headers() -> dict:
    return {"Authorization": f"Bearer {ARK_API_KEY}", "Content-Type": "application/json"}


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
# Translation
# ---------------------------------------------------------------------------
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


def translate_request(body: dict, model_id: str) -> dict:
    """Map an OpenRouter /api/v1/videos request onto a BytePlus create-task body.

    OpenRouter (client-facing) fields:
      model, prompt, duration|seconds, resolution|size, aspect_ratio, seed,
      generate_audio, watermark, camera_fixed, output_format, frames,
      frame_images[], input_references[], provider (passthrough)

    `model_id` is the resolved provider-side model id; the slug -> id lookup and
    its 404 belong to the registry, not here.

    `callback_url` is accepted and deliberately ignored — see invariant 4 in
    CLAUDE.md. ModelArk does support it natively, but forwarding it would emit
    BytePlus-shaped payloads to the client instead of OpenRouter events.
    """
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

    bp_body: dict = {"model": model_id, "content": content}

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


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
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
# Provider
# ---------------------------------------------------------------------------
class BytePlusProvider:
    name = "byteplus"

    def require_config(self) -> None:
        if not ARK_API_KEY:
            raise HTTPException(status_code=500, detail="ARK_API_KEY not configured")

    def upstream(self) -> str:
        return ARK_BASE_URL

    async def submit(self, client: httpx.AsyncClient, body: dict, model_id: str) -> str:
        bp_body = translate_request(body, model_id)
        r = await client.post(
            f"{ARK_BASE_URL}{ARK_CREATE_TASK_PATH}", headers=ark_headers(), json=bp_body
        )
        if r.status_code >= 400:
            # ModelArk validates strictly; pass its message through so the caller
            # learns exactly which knob their model rejected.
            payload = _safe_json(r)
            raise UpstreamError(r.status_code, payload.get("error", payload))

        task_id = extract_task_id(r.json())
        if not task_id:
            raise HTTPException(status_code=502, detail="BytePlus did not return a task id")
        return task_id

    async def poll(self, client: httpx.AsyncClient, task_id: str) -> dict:
        r = await client.get(
            f"{ARK_BASE_URL}{ark_retrieve_task_path(task_id)}", headers=ark_headers()
        )
        if r.status_code >= 400:
            raise HTTPException(status_code=r.status_code, detail=_safe_json(r))
        bp = r.json()

        status = extract_status(bp)
        out = {"status": status, "urls": [], "last_frame_url": None, "error": None}
        if status == "completed":
            out["urls"] = extract_result_urls(bp)
            out["last_frame_url"] = extract_last_frame_url(bp)
        elif status == "failed":
            out["error"] = extract_error(bp)
        return out
