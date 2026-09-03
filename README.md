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
| GET    | `/api/v1/videos/{id}/content?index=0` | `302` to the presigned video URL           |
| GET    | `/api/v1/videos/models`               | List mapped models                         |
| POST   | `/api/v1/prompts/optimize`            | Rewrite a prompt, generate nothing         |
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

# or run the whole flow: submit -> poll -> download
ROUTER_KEY=test-key-123 ./smoke_test.sh
```

Defaults to the flagship, Seedance 2.5 at 720p/5s. `DURATION` is pinned on
purpose — 2.5 defaults to `-1`, which lets the model pick any length up to 30s,
making an unpinned run slow and unpredictably priced.

Longer showcase clip (~8 minutes):

```bash
ROUTER_KEY=test-key-123 DURATION=25 ./smoke_test.sh
```

Cheap, fast variant for CI or a post-deploy check (~2 minutes, cents):

```bash
ROUTER_KEY=test-key-123 MODEL=bytedance/seedance-2.0-mini ./smoke_test.sh
```

The video lands in `./smoke-output/<timestamp>.mp4`.

## Deploy to any cloud

The image is a stateless HTTP server on `$PORT` with no volumes or database, so
it runs unchanged on Cloud Run, Render, Railway, Fly, ECS, or a plain VM.

1. Build & push: `docker build -t <registry>/second-router . && docker push <registry>/second-router`
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

Result URLs are presigned and **expire after 24 hours**. Store the bytes yourself
if you need them longer.

## Prompt optimization

**Off by default.** Opt in per request:

```json
{"model": "bytedance/seedance-2.5", "prompt": "cat surfing", "optimize_prompt": true}
```

The prompt is rewritten by `seed-2-0-pro-260328` before generation, using the
vendor prompt guide that matches the target model as the system prompt. The guides
live in `optimizer/skills/` — replacing a file changes the behaviour, no code edit.

| Target model | Skill |
|---|---|
| `seedance-2.5` | `sd25-pe` |
| `seedance-2.0`, `-fast`, `-mini`, `seedance-1.5-pro` | `sd20-pe` |
| any Seedance with `omni_reference_task_type: "edit"` | `sd-editing` |
| `seedream-*` | `sd5-pe` |

The 202 response reports what happened:

```json
{"id": "...", "status": "pending",
 "prompt_optimization": {"applied": true, "skill": "sd20-pe", "error": null,
                         "prompt": "A fluffy domestic tabby cat balances..."}}
```

**Failures are non-fatal.** A timeout, a bad model id or an unreachable endpoint
leaves the original prompt in place and puts the reason in `error`; the generation
still runs. The key is absent from the response entirely when optimization was not
requested.

Operators can flip the default with `OPTIMIZER_DEFAULT=on`; a per-request
`optimize_prompt` always wins. `GET /healthz` reports the active default, model and
loaded skills.

### Optimize without generating

Generation costs dollars and minutes; optimization costs cents and seconds. Use the
standalone endpoint to preview, edit, and reuse a prompt across models before
spending anything:

```bash
curl -X POST localhost:8080/api/v1/prompts/optimize   -H "Authorization: Bearer test-key-123" -H "Content-Type: application/json"   -d '{"model":"bytedance/seedance-2.5","prompt":"cat surfing chased by a shark"}'
```

```json
{"model": "bytedance/seedance-2.5", "prompt": "A fluffy tabby cat balances...",
 "applied": true, "skill": "sd25-pe",
 "usage": {"prompt_tokens": 19279, "completion_tokens": 478, "total_tokens": 19757},
 "error": null}
```

Here a failure is a failed request (`502`), because optimization *is* the request —
but the original prompt still comes back in the body so you can fall back
deliberately. That is the opposite of the submit path, where a failed optimization
must never block generation.

**Measured cost per call**, from the `usage` block:

| Skill | Prompt tokens |
|---|---|
| `sd25-pe` (Seedance 2.5) | ~19,300 |
| `sd20-pe` (Seedance 2.0 / 1.5) | ~2,800 |
| `sd-editing` | ~660 |
| `sd5-pe` (Seedream) | ~2,100 |

The 2.5 guide is 7× the next largest. If that cost matters at volume, trimming
`optimizer/skills/sd25-skill.md` is the lever.

### Using a different LLM

`OPTIMIZER_BASE_URL` and `OPTIMIZER_API_KEY` default to the ModelArk values but are
read separately: the rewriting model and the generation provider are independent
axes. Point them at any OpenAI-compatible chat endpoint and nothing else changes.

## Downloading the result

`GET /api/v1/videos/{id}/content` returns a **302** to the presigned asset URL.
The client fetches the bytes straight from storage, so the router never carries
them — a 25s/720p clip is ~41 MB, and proxying that per request is the first
thing to fall over under load. Storage serves range requests, so seeking works.

This discloses nothing extra: the same URL is already in `unsigned_urls` on the
poll response. No auth header of ours travels to the CDN, and well-behaved
clients (curl, browsers) drop `Authorization` on a cross-host redirect.

**Your clients must be able to reach the asset host directly.** Follow redirects
(`curl -L`), or just use the `unsigned_urls` from the poll response.

```bash
curl -L -o out.mp4 "localhost:8080/api/v1/videos/<id>/content" -H "Authorization: Bearer test-key-123"
```