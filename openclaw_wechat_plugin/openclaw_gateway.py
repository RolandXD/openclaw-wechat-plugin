from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from .config import (
    BACKEND_BASE_URL,
    OPENCLAW_APPLY_AFTER_REGISTER,
    OPENCLAW_CLIENT_ID,
    OPENCLAW_CLIENT_MODE,
    OPENCLAW_GATEWAY_WS_URL,
    OPENCLAW_PLUGIN_ENTRY_KEY,
    OPENCLAW_ROLE,
    OPENCLAW_TIMEOUT,
    OPENCLAW_TOKEN,
)

logger = logging.getLogger(__name__)


class OpenClawGatewayClient:
    SCOPES = ["operator.admin", "operator.approvals", "operator.pairing"]
    PROTOCOL = 3

    def __init__(self) -> None:
        self.ws_url = OPENCLAW_GATEWAY_WS_URL
        self.token = OPENCLAW_TOKEN
        self.timeout = OPENCLAW_TIMEOUT
        self.apply_after_register = OPENCLAW_APPLY_AFTER_REGISTER
        self.plugin_entry_key = OPENCLAW_PLUGIN_ENTRY_KEY

    async def register_wechat_plugin(self, plugin_base_url: str) -> dict[str, Any]:
        if not self.ws_url:
            raise RuntimeError("OPENCLAW_GATEWAY_WS_URL is empty")
        if not self.token:
            raise RuntimeError("OPENCLAW_TOKEN is empty")

        event_buffer: deque[dict[str, Any]] = deque()

        try:
            async with websockets.connect(
                self.ws_url,
                open_timeout=self.timeout,
                close_timeout=5,
                max_size=8 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                await self._capture_connect_challenge(
                    ws=ws,
                    event_buffer=event_buffer,
                    timeout=min(2.0, self.timeout),
                )

                hello = await self._request(
                    ws=ws,
                    method="connect",
                    params=self._connect_params(),
                    event_buffer=event_buffer,
                    timeout=self.timeout,
                )

                schema_payload = await self._request(
                    ws=ws,
                    method="config.schema",
                    params={},
                    event_buffer=event_buffer,
                    timeout=self.timeout,
                )
                if not self._schema_has_plugin_entry(
                    schema_payload=schema_payload,
                    plugin_entry_key=self.plugin_entry_key,
                ):
                    raise RuntimeError(
                        "OpenClaw plugin `wechat` is not installed on this host. "
                        "Run `openclaw-wechat-plugin install-openclaw` (or "
                        "`openclaw plugins install <extension-path>`), then retry."
                    )

                config_snapshot = await self._request(
                    ws=ws,
                    method="config.get",
                    params={},
                    event_buffer=event_buffer,
                    timeout=self.timeout,
                )

                base_hash = config_snapshot.get("hash")
                config_obj = config_snapshot.get("config")

                if not isinstance(base_hash, str) or not base_hash.strip():
                    raise RuntimeError("OpenClaw config hash missing")
                if not isinstance(config_obj, dict):
                    raise RuntimeError("OpenClaw config payload is invalid")

                changed, entry_config = self._upsert_wechat_entry(
                    config_obj=config_obj,
                    plugin_base_url=plugin_base_url,
                )

                if not changed:
                    return {
                        "changed": False,
                        "action": "noop",
                        "plugin_entry": self.plugin_entry_key,
                        "entry_config": entry_config,
                    }

                raw = json.dumps(config_obj, ensure_ascii=False, indent=2)
                write_method = "config.apply" if self.apply_after_register else "config.set"
                params: dict[str, Any] = {
                    "raw": raw,
                    "baseHash": base_hash,
                }
                if write_method == "config.apply":
                    session_key = self._resolve_main_session_key(hello)
                    if session_key:
                        params["sessionKey"] = session_key

                await self._request(
                    ws=ws,
                    method=write_method,
                    params=params,
                    event_buffer=event_buffer,
                    timeout=self.timeout,
                )

                return {
                    "changed": True,
                    "action": write_method,
                    "plugin_entry": self.plugin_entry_key,
                    "entry_config": entry_config,
                }
        except ConnectionClosed as exc:
            raise RuntimeError(
                f"OpenClaw gateway disconnected: code={exc.code}, reason={exc.reason}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"OpenClaw gateway connection failed: {exc}") from exc

    def _connect_params(self) -> dict[str, Any]:
        return {
            "minProtocol": self.PROTOCOL,
            "maxProtocol": self.PROTOCOL,
            "client": {
                "id": OPENCLAW_CLIENT_ID,
                "version": "wechat-plugin/0.2",
                "platform": "python",
                "mode": OPENCLAW_CLIENT_MODE,
                "instanceId": str(uuid.uuid4()),
            },
            "role": OPENCLAW_ROLE,
            "scopes": self.SCOPES,
            "caps": [],
            "auth": {"token": self.token},
        }

    def _upsert_wechat_entry(
        self,
        config_obj: dict[str, Any],
        plugin_base_url: str,
    ) -> tuple[bool, dict[str, Any]]:
        changed = False

        plugins = config_obj.get("plugins")
        if not isinstance(plugins, dict):
            plugins = {}
            config_obj["plugins"] = plugins
            changed = True

        entries = plugins.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            plugins["entries"] = entries
            changed = True

        entry = entries.get(self.plugin_entry_key)
        if not isinstance(entry, dict):
            entry = {}
            entries[self.plugin_entry_key] = entry
            changed = True

        if entry.get("enabled") is not True:
            entry["enabled"] = True
            changed = True

        entry_config = entry.get("config")
        if not isinstance(entry_config, dict):
            entry_config = {}
            entry["config"] = entry_config
            changed = True

        desired = {
            "adapterUrl": plugin_base_url,
            "backendBaseUrl": BACKEND_BASE_URL,
            "mode": "external-forward",
        }
        for key, value in desired.items():
            if entry_config.get(key) != value:
                entry_config[key] = value
                changed = True

        return changed, entry_config

    async def _capture_connect_challenge(
        self,
        ws: Any,
        event_buffer: deque[dict[str, Any]],
        timeout: float,
    ) -> None:
        try:
            packet = await self._recv_json(ws, timeout=timeout)
        except TimeoutError:
            return

        if packet:
            event_buffer.append(packet)

    @staticmethod
    def _resolve_main_session_key(hello_payload: dict[str, Any]) -> Optional[str]:
        snapshot = hello_payload.get("snapshot")
        if not isinstance(snapshot, dict):
            return None
        session_defaults = snapshot.get("sessionDefaults")
        if not isinstance(session_defaults, dict):
            return None
        value = session_defaults.get("mainSessionKey")
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    async def _request(
        self,
        ws: Any,
        method: str,
        params: dict[str, Any],
        event_buffer: deque[dict[str, Any]],
        timeout: float,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        await ws.send(
            json.dumps(
                {
                    "type": "req",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
                ensure_ascii=False,
            )
        )

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"OpenClaw {method} timeout after {timeout}s")

            packet = await self._recv_json(ws, timeout=remaining)
            if packet.get("type") == "event":
                event_buffer.append(packet)
                continue

            if packet.get("type") != "res" or packet.get("id") != request_id:
                continue

            if packet.get("ok"):
                payload = packet.get("payload")
                if isinstance(payload, dict):
                    return payload
                return {"value": payload}

            error = packet.get("error")
            code = "UNKNOWN"
            message = "request failed"
            if isinstance(error, dict):
                code = str(error.get("code") or code)
                message = str(error.get("message") or message)
            raise RuntimeError(f"OpenClaw {method} failed [{code}]: {message}")

    async def _recv_json(self, ws: Any, timeout: float) -> dict[str, Any]:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timed out waiting for OpenClaw gateway frame") from exc

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        try:
            packet = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Ignoring non-JSON gateway frame: %s", raw)
            return {}

        if isinstance(packet, dict):
            return packet
        return {}

    @staticmethod
    def _schema_has_plugin_entry(
        *,
        schema_payload: dict[str, Any],
        plugin_entry_key: str,
    ) -> bool:
        schema = schema_payload.get("schema")
        if not isinstance(schema, dict):
            return False

        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return False

        plugins = properties.get("plugins")
        if not isinstance(plugins, dict):
            return False

        plugin_properties = plugins.get("properties")
        if not isinstance(plugin_properties, dict):
            return False

        entries = plugin_properties.get("entries")
        if not isinstance(entries, dict):
            return False

        entry_properties = entries.get("properties")
        if not isinstance(entry_properties, dict):
            return False

        return plugin_entry_key in entry_properties


openclaw_gateway_client = OpenClawGatewayClient()
