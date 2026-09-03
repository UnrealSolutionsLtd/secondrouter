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

import os
import pathlib

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


async def optimize(client: httpx.AsyncClient, prompt: str, slug: str, body: dict) -> dict:
    """Returns {"prompt": str, "applied": bool, "skill": str|None, "error": str|None}.

    The original prompt is returned unchanged on any failure.
    """
    unchanged = {"prompt": prompt, "applied": False, "skill": None,
                 "error": None, "usage": None}
    if not prompt:
        return {**unchanged, "error": "no prompt to optimize"}
    if not OPTIMIZER_API_KEY:
        return {**unchanged, "error": "OPTIMIZER_API_KEY / ARK_API_KEY not configured"}

    skill = pick_skill(slug, task_of(body))
    if skill is None:
        return {**unchanged, "error": f"no skill covers model '{slug}'"}

    payload = {
        "model": OPTIMIZER_MODEL,
        "messages": [
            {"role": "system", "content": skill["text"]},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": OPTIMIZER_MAX_TOKENS,
    }
    try:
        r = await client.post(
            f"{OPTIMIZER_BASE_URL}{OPTIMIZER_PATH}",
            headers={"Authorization": f"Bearer {OPTIMIZER_API_KEY}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=OPTIMIZER_TIMEOUT,
        )
        if r.status_code >= 400:
            return {**unchanged, "skill": skill["name"],
                    "error": f"optimizer HTTP {r.status_code}"}
        data = r.json()
        usage = data.get("usage")
        text = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        return {**unchanged, "skill": skill["name"],
                "error": f"{type(e).__name__}: {e}"[:200]}

    if not text:
        return {**unchanged, "skill": skill["name"], "error": "optimizer returned empty text"}
    return {"prompt": text, "applied": True, "skill": skill["name"],
            "error": None, "usage": usage}
