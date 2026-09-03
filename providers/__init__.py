"""Provider registry — resolves a model slug or a job id to a provider.

`models.yaml` is the allowlist. Each entry may name its backend:

    models:
      - openrouter: bytedance/seedance-2.5
        byteplus: dreamina-seedance-2-5-260628
        provider: byteplus          # optional, defaults to byteplus

The provider-side model id is read from a key named after the provider
(`byteplus:` above), so adding a second provider does not disturb existing
entries.
"""

import yaml
from fastapi import HTTPException

from .byteplus import BytePlusProvider

DEFAULT_PROVIDER = "byteplus"

#: name -> provider instance
PROVIDERS = {p.name: p for p in (BytePlusProvider(),)}

#: OpenRouter slug -> (provider name, provider-side model id)
MODEL_MAP: dict[str, tuple[str, str]] = {}


def _load(path: str = "models.yaml") -> None:
    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return
    for m in (cfg.get("models") or []):
        name = m.get("provider", DEFAULT_PROVIDER)
        model_id = m.get(name)
        if not model_id or name not in PROVIDERS:
            continue
        MODEL_MAP[m["openrouter"]] = (name, model_id)


_load()


def slugs() -> list[str]:
    return sorted(MODEL_MAP)


def catalog() -> list[dict]:
    return [
        {"id": slug, "provider": name, "backend": model_id}
        for slug, (name, model_id) in MODEL_MAP.items()
    ]


def for_slug(slug: str | None):
    """Resolve a client-facing slug. Returns (provider, provider-side model id)."""
    entry = MODEL_MAP.get(slug or "")
    if not entry:
        raise HTTPException(status_code=404, detail=f"no endpoints found for model '{slug}'")
    name, model_id = entry
    return PROVIDERS[name], model_id


def for_name(name: str):
    """Resolve the provider tag carried in a job id."""
    provider = PROVIDERS.get(name)
    if provider is None:
        raise HTTPException(status_code=404, detail="unknown job id")
    return provider


def upstreams() -> dict:
    return {name: p.upstream() for name, p in PROVIDERS.items()}


def upstream() -> str | None:
    """Default provider's base URL — keeps /healthz shaped as it always was."""
    p = PROVIDERS.get(DEFAULT_PROVIDER) or next(iter(PROVIDERS.values()), None)
    return p.upstream() if p else None
