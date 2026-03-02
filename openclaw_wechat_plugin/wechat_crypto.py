from __future__ import annotations

import hashlib
from typing import Any


def verify_signature(token: str, signature: str, timestamp: str, nonce: str) -> bool:
    payload = "".join(sorted([token, timestamp, nonce]))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest == signature


def ensure_json_object(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise ValueError("Request body must be a JSON object")
    return body
