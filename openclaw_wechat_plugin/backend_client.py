from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from .config import (
    BACKEND_BASE_URL,
    BACKEND_HEARTBEAT_PATH,
    BACKEND_MESSAGE_PATH,
    BACKEND_REGISTER_PATH,
    BACKEND_TIMEOUT,
    HOST,
    PLUGIN_INSTANCE_ID,
    PLUGIN_NAME,
    PLUGIN_PUBLIC_BASE_URL,
    PLUGIN_REGISTRY_TOKEN,
    PLUGIN_VERSION,
    PORT,
)
from .models import PluginRegisterPayload

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self) -> None:
        self.base_url = BACKEND_BASE_URL
        self.message_url = self._join_path(BACKEND_MESSAGE_PATH)
        self.register_url = self._join_path(BACKEND_REGISTER_PATH)
        self.timeout = BACKEND_TIMEOUT

    @staticmethod
    def _join_path(path: str) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        return f"{BACKEND_BASE_URL}{normalized}"

    @staticmethod
    def _registry_headers() -> dict[str, str]:
        headers: dict[str, str] = {}
        if PLUGIN_REGISTRY_TOKEN:
            headers["x-plugin-registry-token"] = PLUGIN_REGISTRY_TOKEN
        return headers

    @staticmethod
    def _plugin_base_url_for_registry() -> str:
        if PLUGIN_PUBLIC_BASE_URL:
            return PLUGIN_PUBLIC_BASE_URL
        if HOST in {"0.0.0.0", "::"}:
            return f"http://127.0.0.1:{PORT}"
        return f"http://{HOST}:{PORT}"

    async def forward_message(
        self,
        payload: dict[str, Any],
        *,
        signature: Optional[str],
        timestamp: Optional[str],
        nonce: Optional[str],
    ) -> dict[str, Any]:
        params: dict[str, str] = {}
        if signature and timestamp and nonce:
            params = {
                "signature": signature,
                "timestamp": timestamp,
                "nonce": nonce,
            }

        headers = {
            "x-weclaw-plugin": PLUGIN_NAME,
            "x-weclaw-plugin-instance": PLUGIN_INSTANCE_ID,
            "x-weclaw-plugin-version": PLUGIN_VERSION,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.message_url,
                    json=payload,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Backend timeout after {self.timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise RuntimeError(
                f"Backend HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Backend request failed: {exc}") from exc

    async def register(self) -> dict[str, Any]:
        payload = PluginRegisterPayload(
            plugin_name=PLUGIN_NAME,
            instance_id=PLUGIN_INSTANCE_ID,
            base_url=self._plugin_base_url_for_registry(),
            version=PLUGIN_VERSION,
            capabilities=[
                "wechat.callback.verify",
                "wechat.message.forward",
                "wechat.signature.verify",
            ],
            metadata={
                "forward_message_path": BACKEND_MESSAGE_PATH,
                "runtime": "fastapi",
            },
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.register_url,
                    json=payload.model_dump(),
                    headers=self._registry_headers(),
                )
                response.raise_for_status()
                result = response.json()
                logger.info("Plugin registry success: %s", result)
                return result
        except Exception as exc:
            logger.warning("Plugin registry failed: %s", exc)
            raise

    async def heartbeat(self) -> dict[str, Any]:
        heartbeat_path = BACKEND_HEARTBEAT_PATH.format(instance_id=PLUGIN_INSTANCE_ID)
        heartbeat_url = self._join_path(heartbeat_path)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    heartbeat_url,
                    headers=self._registry_headers(),
                )
                response.raise_for_status()
                result = response.json()
                logger.debug("Plugin heartbeat success: %s", result)
                return result
        except Exception as exc:
            logger.warning("Plugin heartbeat failed: %s", exc)
            raise


backend_client = BackendClient()
