"""The interface every provider implements.

Deliberately small: it is exactly what `app.py` needs and nothing more. The
shared `httpx.AsyncClient` is passed in rather than owned per provider, so pool
limits and timeouts stay configured in one place.

`poll()` returns a normalized dict so the HTTP surface never sees a
provider-shaped payload:

    {
      "status": one of pending | processing | completed | failed | expired,
      "urls": [str, ...],          # present when completed, else []
      "last_frame_url": str|None,  # optional extra asset
      "error": str|None,           # present when failed
    }
"""

from typing import Protocol

import httpx


class UpstreamError(Exception):
    """Provider rejected the request. `app.py` renders it as {"error": ...},
    which is the envelope clients have always seen on submit."""

    def __init__(self, status_code: int, payload):
        super().__init__(f"upstream {status_code}")
        self.status_code = status_code
        self.payload = payload


class Provider(Protocol):
    #: Registry key, and the value stored in the job id's provider tag.
    name: str

    def require_config(self) -> None:
        """Raise if the provider is missing credentials or config."""

    async def submit(self, client: httpx.AsyncClient, body: dict, model_id: str) -> str:
        """Create a generation task upstream and return its task id."""

    async def poll(self, client: httpx.AsyncClient, task_id: str) -> dict:
        """Fetch a task and return the normalized shape documented above."""

    def upstream(self) -> str:
        """Base URL, for /healthz."""
