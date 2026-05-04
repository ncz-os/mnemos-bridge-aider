from __future__ import annotations

import os
import uuid

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("MNEMOS_TEST_BASE"),
    reason="requires live MNEMOS",
)


def _headers() -> dict[str, str]:
    token = os.getenv("MNEMOS_API_KEY") or os.getenv("MNEMOS_TEST_API_KEY")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def test_path_a_rest_workflow_against_live_mnemos():
    # Path B plugin integration is intentionally not covered here because the
    # Aider plugin API is unstable across versions. This integration test keeps
    # the stable Path A REST workflow honest against a live MNEMOS/PYTHIA target.
    base = os.environ["MNEMOS_TEST_BASE"].rstrip("/")
    content = f"mnemos-bridge-aider integration test {uuid.uuid4()}"

    with httpx.Client(base_url=base, headers=_headers(), timeout=30) as client:
        created = client.post("/memories", json={"content": content, "category": "test"})
        created.raise_for_status()
        created_payload = created.json()
        memory_id = created_payload.get("id") or created_payload.get("memory_id")
        assert memory_id

        fetched = client.get(f"/memories/{memory_id}")
        fetched.raise_for_status()
        assert content in str(fetched.json())

        searched = client.post("/memories/search", json={"query": content, "limit": 5})
        searched.raise_for_status()
        assert content in str(searched.json())

        listed = client.get("/memories", params={"limit": 5})
        listed.raise_for_status()
        assert listed.json()
