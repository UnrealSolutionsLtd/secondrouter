# Second router

An OpenRouter-compatible **video generation** API with a **BytePlus ModelArk**
backend. Stateless, single container, deployable locally or to any cloud.

Clients call OpenRouter's video contract; the service translates each call to a
BytePlus create/retrieve task and returns results in OpenRouter's shape.

## Endpoints

| Method | Path                                  | Purpose                                    |
|--------|---------------------------------------|--------------------------------------------|
| POST   | `/api/v1/videos`                      | Submit a job → `{id, polling_url, status}` |
| GET    | `/api/v1/videos/{id}`                 | Poll status → result URLs when done        |
| GET    | `/api/v1/videos/{id}/content?index=0` | Stream the MP4                             |
| GET    | `/api/v1/videos/models`               | List mapped models                         |
| GET    | `/healthz`                            | Liveness                                   |

Auth: every call needs `Authorization: Bearer <one of ROUTER_KEYS>`. The BytePlus
key is injected server-side and never exposed.

**Stateless by design:** the BytePlus task id is encoded inside the job `id`, so
there's no database — scale to zero or run many replicas freely.

## Run locally

```bash
cp .env.example .env          # set ARK_API_KEY, keep ROUTER_KEYS
pip install -r requirements.txt
uvicorn app:app --port 8080
```

Or one command with Docker:

```bash
cp .env.example .env          # set ARK_API_KEY
docker compose up --build
```

## Test

```bash
curl localhost:8080/healthz

# submit
curl -X POST localhost:8080/api/v1/videos \
  -H "Authorization: Bearer test-key-123" -H "Content-Type: application/json" \
  -d '{"model":"bytedance/seedance-2.5","prompt":"a cat surfing, cinematic"}'

# poll (use the id from above)
curl localhost:8080/api/v1/videos/<id> -H "Authorization: Bearer test-key-123"

# or run the whole flow
ROUTER_KEY=test-key-123 MODEL=bytedance/seedance-2.5 ./smoke_test.sh
```

## Deploy to any cloud

The image is a stateless HTTP server on `$PORT` with no volumes or database, so
it runs unchanged on Cloud Run, Render, Railway, Fly, ECS, or a plain VM.

1. Build & push: `docker build -t <registry>/video-router . && docker push <registry>/video-router`
2. Run with env vars: `ARK_API_KEY`, `ROUTER_KEYS`, `ARK_BASE_URL`, and
   **`PUBLIC_BASE_URL`** set to the service's public https URL (so `polling_url`
   is correct behind a load balancer).
3. Most platforms inject `PORT` automatically; the container honors it.

## Request options

Beyond `model` and `prompt`, these are forwarded to BytePlus. Support varies by
model — the router forwards what you send and returns BytePlus's own validation
error verbatim, so an unsupported knob gives you a precise 400.

| Field | Notes |
|---|---|
| `duration` (or `seconds`) | Seconds. `-1` lets the model choose. Ranges differ per model. |
| `resolution` (or `size`) | `480p`, `720p`, `1080p`; `4k` on Seedance 2.0 only. |
| `aspect_ratio` (or `ratio`) | `16:9`, `4:3`, `1:1`, `3:4`, `9:16`, `21:9`, `adaptive`. |
| `generate_audio` | Default `true` — the video comes back with sound. |
| `watermark`, `seed`, `camera_fixed`, `frames`, `output_format`, `draft` | Passed straight through. |
| `return_last_frame` | Adds `last_frame_url` to the completed response. |
| `frame_images[]` | `{url, frame_type: first_frame \| last_frame}` — image-to-video. |
| `input_references[]` | `{url, type: image \| video \| audio}` — omni reference-to-video (Seedance 2.x). |
| `provider.byteplus_extra` | Escape hatch: merged into the upstream body untouched. |

`frame_images` and `input_references` are mutually exclusive task types and
cannot be combined. `callback_url` is accepted and ignored — polling only.

Result URLs are presigned and **expire after 24 hours**. Fetch through
`/content`, or store the bytes yourself.