"""Prompt optimization — rewrite the caller's prompt with an LLM before generation.

OFF by default. A request opts in with `"optimize_prompt": true`; the operator can
flip the default with OPTIMIZER_DEFAULT=on.

How it works: pick the skill that matches the target model (and whether this is an
edit), send it as the system prompt to Seed 2.0 Pro on ModelArk's chat endpoint,
and use the reply as the prompt. The skills in `optimizer/skills/` are the vendor's
own prompt guides — they are the whole of the optimizer's knowledge, and swapping a
file changes behaviour without touching code.

Failure is never fatal: if the LLM call errors or times out, the original prompt is
used and the reason is reported back on the submit response. A prompt enhancer that
can take down generation is worse than no enhancer.
"""

import json
import os
import pathlib
import re

import httpx

SKILL_DIR = pathlib.Path(__file__).parent / "skills"

# The rewriting LLM and the generation provider are independent axes: you can
# optimize a Seedance prompt with any OpenAI-compatible chat model. By default the
# optimizer reuses the ModelArk credentials, but naming these separately keeps the
# seam visible — point them elsewhere and nothing else changes.
_ARK_BASE_URL = os.environ.get(
    "ARK_BASE_URL", "https://ark.ap-southeast.bytepluses.com/api/v3"
).rstrip("/")
OPTIMIZER_BASE_URL = (os.environ.get("OPTIMIZER_BASE_URL") or _ARK_BASE_URL).rstrip("/")
OPTIMIZER_API_KEY = os.environ.get("OPTIMIZER_API_KEY") or os.environ.get("ARK_API_KEY")
OPTIMIZER_PATH = os.environ.get("OPTIMIZER_PATH", "/chat/completions")
OPTIMIZER_MODEL = os.environ.get("OPTIMIZER_MODEL", "seed-2-0-pro-260328")
OPTIMIZER_TIMEOUT = float(os.environ.get("OPTIMIZER_TIMEOUT", "120"))
OPTIMIZER_MAX_TOKENS = int(os.environ.get("OPTIMIZER_MAX_TOKENS", "2048"))
#: Ask the API to enforce the schema. Verified working on seed-2-0-pro even
#: though ModelArk's structured-output table does not list it. Turn off for a
#: backend that rejects response_format; the text contract still applies.
OPTIMIZER_JSON = os.environ.get("OPTIMIZER_JSON", "on").strip().lower() in (
    "1", "on", "true", "yes"
)

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "optimized_prompt",
        "schema": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
            "additionalProperties": False,
        },
    },
}
#: Per-request `optimize_prompt` always wins; this is only the fallback.
OPTIMIZER_DEFAULT = os.environ.get("OPTIMIZER_DEFAULT", "off").strip().lower() in (
    "1", "on", "true", "yes"
)

# Client slug -> the token the skills use in their `models:` frontmatter.
# seedance-1.5-pro has no published guide of its own; the 2.0 guide is the closest
# documented behaviour, so it borrows that one.
SLUG_TOKENS = {
    "bytedance/seedance-2.5": "seedance25",
    "bytedance/seedance-2.0": "seedance",
    "bytedance/seedance-2.0-fast": "seedanceFast",
    "bytedance/seedance-2.0-mini": "seedanceMini",
    "bytedance/seedance-1.5-pro": "seedance",
    "bytedance/seedream-5.0-pro": "seedreamPro",
    "bytedance/seedream-5.0": "seedream",
    "bytedance/seedream-5.0-lite": "seedream",
}

# Appended to every skill as the last thing the model reads. The skills are written
# for a chat agent that may narrate, use headings or fence its answer; here the reply
# is fed straight into a generation request, so it must be the prompt and nothing
# else. Stated last and marked as overriding, because later instructions win.
OUTPUT_CONTRACT = """

---

# OUTPUT CONTRACT — overrides any formatting instruction above

Your reply is parsed by a program and inserted directly into a generation request.
It is never read by a human first.

Reply with a single JSON object and nothing else:

{"prompt": "<the finished prompt as one string>"}

Rules:

- Output raw JSON. No code fence, no backticks, no commentary before or after.
- Exactly one key, "prompt". No notes, no explanation of what you changed.
- The value is the finished prompt as plain text. Inside it use no markdown, no
  headings, no bullets and no numbering; write plain sentences. Line breaks inside
  the string must be escaped as \n.
- If you have nothing to add to the input, return the input unchanged as the value.
"""

# sd25-skill.md carries no `models:`/`tasks:` frontmatter, so it is bound by name.
SKILL_BY_NAME = {"seedance25": "sd25-pe"}


def _frontmatter(text: str) -> dict:
    """Parse the small YAML subset the skills use: scalars and `- ` lists."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    meta, key = {}, None
    for line in text[3:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and key:
            meta.setdefault(key, []).append(line[4:].strip())
        elif ":" in line and not line.startswith((" ", "\t")):
            k, _, v = line.partition(":")
            key = k.strip()
            v = v.strip()
            meta[key] = v if v else []
        elif not line.startswith((" ", "\t")):
            key = None
    return meta


def _unfence(text: str) -> str:
    """Safety net behind OUTPUT_CONTRACT: strip a fence if one appears anyway.

    The instruction is the fix; this is the belt to its braces. Without both, the
    backticks and language marker travel into the generation prompt verbatim.
    """
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.splitlines()[1:]                      # drop the opening fence
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]                          # drop the closing fence
    return chr(10).join(lines).strip()


def _extract_prompt(text: str):
    """Pull the prompt out of a JSON reply. Returns (prompt, warning).

    Tries the raw body, then the body with a code fence stripped, then the
    outermost {...} in case the model wrapped the object in prose.
    """
    stripped = _unfence(text)
    candidates = [text.strip(), stripped]
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if m:
        candidates.append(m.group(0))

    for c in candidates:
        if not c:
            continue
        try:
            obj = json.loads(c)
        except Exception:
            continue
        if isinstance(obj, dict):
            p = obj.get("prompt")
            if isinstance(p, str) and p.strip():
                return p.strip(), None
    return None, "reply was not JSON with a string `prompt`"


def _load() -> list[dict]:
    out = []
    for path in sorted(SKILL_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        meta = _frontmatter(body)
        out.append({
            "file": path.name,
            "name": meta.get("name", path.stem),
            "models": meta.get("models") or [],
            "tasks": meta.get("tasks") or [],
            "text": body,
        })
    return out


SKILLS = _load()


def skill_catalog() -> list[dict]:
    return [
        {"file": s["file"], "name": s["name"], "models": s["models"],
         "tasks": s["tasks"], "chars": len(s["text"])}
        for s in SKILLS
    ]


def pick_skill(slug: str, task: str = "generate") -> dict | None:
    """Most specific match wins: a skill that names this task beats one that
    names none. Returns None when nothing covers the model."""
    token = SLUG_TOKENS.get(slug)
    if not token:
        return None

    by_name = SKILL_BY_NAME.get(token)
    candidates = [s for s in SKILLS if token in s["models"]]
    if by_name:
        candidates += [s for s in SKILLS if s["name"] == by_name]

    exact = [s for s in candidates if task in s["tasks"]]
    if exact:
        return exact[0]
    generic = [s for s in candidates if not s["tasks"]]
    if generic:
        return generic[0]
    return candidates[0] if candidates else None


def task_of(body: dict) -> str:
    """`omni_reference_task_type` is a real ModelArk field we already forward."""
    return "edit" if str(body.get("omni_reference_task_type", "")).lower() == "edit" else "generate"


def wanted(body: dict) -> bool:
    flag = body.get("optimize_prompt")
    return OPTIMIZER_DEFAULT if flag is None else bool(flag)


async def _chat(client: httpx.AsyncClient, messages: list, max_tokens: int) -> tuple:
    """POST to the chat endpoint. Returns (text, usage) or raises."""
    payload = {"model": OPTIMIZER_MODEL, "messages": messages, "max_tokens": max_tokens}
    if OPTIMIZER_JSON:
        payload["response_format"] = RESPONSE_FORMAT
    r = await client.post(
        f"{OPTIMIZER_BASE_URL}{OPTIMIZER_PATH}",
        headers={"Authorization": f"Bearer {OPTIMIZER_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=OPTIMIZER_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"optimizer HTTP {r.status_code}")
    data = r.json()
    return data["choices"][0]["message"]["content"] or "", data.get("usage")


REPAIR_SYSTEM = (
    "You convert a malformed reply into JSON. Output exactly one JSON object of the "
    'form {"prompt": "<text>"} and nothing else. Put the generation prompt that the '
    "input contains into the value, verbatim, minus any markdown, headings, labels "
    "or commentary. Output raw JSON with no code fence."
)


async def _repair(client: httpx.AsyncClient, bad: str) -> tuple:
    """Second chance at JSON without re-sending the skill.

    Re-running the skill would cost another ~19k prompt tokens on sd25; this costs
    a few hundred, because the content is already written — only the shape is wrong.
    """
    return await _chat(client, [
        {"role": "system", "content": REPAIR_SYSTEM},
        {"role": "user", "content": bad[:12000]},
    ], max_tokens=OPTIMIZER_MAX_TOKENS)


async def optimize(client: httpx.AsyncClient, prompt: str, slug: str, body: dict) -> dict:
    """Returns {"prompt": str, "applied": bool, "skill": str|None, "error": str|None}.

    The original prompt is returned unchanged on any failure.
    """
    unchanged = {"prompt": prompt, "applied": False, "skill": None,
                 "error": None, "warning": None, "usage": None, "attempts": 0}
    if not prompt:
        return {**unchanged, "error": "no prompt to optimize"}
    if not OPTIMIZER_API_KEY:
        return {**unchanged, "error": "OPTIMIZER_API_KEY / ARK_API_KEY not configured"}

    skill = pick_skill(slug, task_of(body))
    if skill is None:
        return {**unchanged, "error": f"no skill covers model '{slug}'"}
    unchanged["skill"] = skill["name"]

    messages = [
        {"role": "system", "content": skill["text"] + OUTPUT_CONTRACT},
        {"role": "user", "content": prompt},
    ]
    try:
        text, usage = await _chat(client, messages, OPTIMIZER_MAX_TOKENS)
    except Exception as e:
        return {**unchanged, "error": f"{type(e).__name__}: {e}"[:200], "attempts": 1}

    out, warning = _extract_prompt(text)
    attempts = 1

    if out is None:
        # The schema was not honoured. Repair the shape without paying for the
        # skill a second time.
        try:
            fixed, usage2 = await _repair(client, text)
            attempts = 2
            out, warning = _extract_prompt(fixed)
            if usage and usage2:
                usage = {k: (usage.get(k, 0) + usage2.get(k, 0))
                         for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
            if out is not None:
                warning = "model ignored the JSON contract; repaired in a second call"
        except Exception as e:
            return {**unchanged, "error": f"repair failed: {type(e).__name__}"[:200],
                    "usage": usage, "attempts": 2}

    if out is None:
        # Never throw away usable text: fall back to the raw reply, but say so.
        salvaged = _unfence(text).strip()
        if not salvaged:
            return {**unchanged, "error": "optimizer returned empty text",
                    "usage": usage, "attempts": attempts}
        return {"prompt": salvaged, "applied": True, "skill": skill["name"],
                "error": None, "usage": usage, "attempts": attempts,
                "warning": "reply was not valid JSON; used the raw text"}

    return {"prompt": out, "applied": True, "skill": skill["name"],
            "error": None, "usage": usage, "attempts": attempts, "warning": warning}
