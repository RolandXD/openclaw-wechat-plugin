from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from .config import (
    CLOUD_TUNNEL_WS_URL,
    CONNECTOR_HEARTBEAT_SECONDS,
    CONNECTOR_LOG_PREFIX,
    CONNECTOR_NODE_ID,
    CONNECTOR_NODE_TOKEN,
    CONNECTOR_OWNER_USER_ID,
    CONNECTOR_RECONNECT_SECONDS,
    LOCAL_OPENCLAW_GATEWAY_WS_URL,
    LOCAL_OPENCLAW_TIMEOUT,
    LOCAL_OPENCLAW_TOKEN,
    OPENCLAW_CLIENT_ID,
    OPENCLAW_CLIENT_MODE,
    OPENCLAW_ROLE,
    PLUGIN_VERSION,
)

logger = logging.getLogger(__name__)


class LocalOpenClawGatewayClient:
    PROTOCOL = 3
    SCOPES = ["operator.admin", "operator.approvals", "operator.pairing"]

    def __init__(self) -> None:
        self.ws_url = LOCAL_OPENCLAW_GATEWAY_WS_URL
        self.timeout = LOCAL_OPENCLAW_TIMEOUT
        self.token = LOCAL_OPENCLAW_TOKEN

    async def chat(
        self,
        *,
        user_message: str,
        conversation_id: Optional[str],
    ) -> dict[str, Any]:
        gateway_timeout = max(15.0, self.timeout)
        event_buffer: deque[dict[str, Any]] = deque()

        async with websockets.connect(
            self.ws_url,
            open_timeout=gateway_timeout,
            close_timeout=5,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await self._capture_connect_challenge(
                ws=ws,
                event_buffer=event_buffer,
                timeout=min(2.0, gateway_timeout),
            )

            hello_payload = await self._gateway_request(
                ws=ws,
                method="connect",
                params=self._build_connect_params(),
                event_buffer=event_buffer,
                timeout=gateway_timeout,
            )

            session_key = self._resolve_session_key(hello_payload, conversation_id)
            if not session_key:
                raise RuntimeError("OpenClaw did not return a valid session key")

            run_id = str(uuid.uuid4())
            chat_send_payload = await self._gateway_request(
                ws=ws,
                method="chat.send",
                params={
                    "sessionKey": session_key,
                    "message": user_message,
                    "deliver": False,
                    "idempotencyKey": run_id,
                },
                event_buffer=event_buffer,
                timeout=gateway_timeout,
            )
            returned_run_id = self._as_non_empty_str(chat_send_payload.get("runId"))
            if returned_run_id:
                run_id = returned_run_id

            final_payload = await self._wait_chat_final_event(
                ws=ws,
                session_key=session_key,
                run_id=run_id,
                event_buffer=event_buffer,
                timeout=gateway_timeout,
            )
            reply_text = self._extract_gateway_message_text(final_payload.get("message"))
            if not reply_text:
                reply_text = self._extract_gateway_message_text(final_payload)

            return {
                "reply": reply_text or "OpenClaw returned empty response.",
                "conversation_id": session_key,
                "run_id": run_id,
            }

    def _build_connect_params(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "minProtocol": self.PROTOCOL,
            "maxProtocol": self.PROTOCOL,
            "client": {
                "id": OPENCLAW_CLIENT_ID,
                "version": f"wechat-connector/{PLUGIN_VERSION}",
                "platform": "python",
                "mode": OPENCLAW_CLIENT_MODE,
                "instanceId": str(uuid.uuid4()),
            },
            "role": OPENCLAW_ROLE,
            "scopes": self.SCOPES,
            "caps": [],
        }
        if self.token:
            payload["auth"] = {"token": self.token}
        return payload

    async def _capture_connect_challenge(
        self,
        *,
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

    async def _gateway_request(
        self,
        *,
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
                return payload if isinstance(payload, dict) else {"value": payload}

            error = packet.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or "UNKNOWN")
                message = str(error.get("message") or "request failed")
                raise RuntimeError(f"OpenClaw {method} failed [{code}]: {message}")
            raise RuntimeError(f"OpenClaw {method} failed")

    async def _wait_chat_final_event(
        self,
        *,
        ws: Any,
        session_key: str,
        run_id: str,
        event_buffer: deque[dict[str, Any]],
        timeout: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        stream_text = ""

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"OpenClaw chat timeout after {timeout}s")

            if event_buffer:
                packet = event_buffer.popleft()
            else:
                packet = await self._recv_json(ws, timeout=remaining)

            if packet.get("type") != "event" or packet.get("event") != "chat":
                continue

            payload = packet.get("payload")
            if not isinstance(payload, dict):
                continue

            payload_session = self._as_non_empty_str(payload.get("sessionKey"))
            if payload_session and payload_session != session_key:
                continue

            payload_run_id = self._as_non_empty_str(payload.get("runId"))
            if payload_run_id and payload_run_id != run_id:
                continue

            state = self._as_non_empty_str(payload.get("state")) or ""
            if state == "delta":
                delta_text = self._extract_gateway_message_text(payload.get("message"))
                if delta_text:
                    stream_text = delta_text
                continue
            if state == "final":
                message_text = self._extract_gateway_message_text(payload.get("message"))
                if message_text:
                    return payload
                if stream_text:
                    payload = dict(payload)
                    payload["message"] = {
                        "role": "assistant",
                        "content": [{"type": "text", "text": stream_text}],
                    }
                    return payload
                return payload
            if state == "error":
                message = self._as_non_empty_str(payload.get("errorMessage")) or "chat error"
                raise RuntimeError(f"OpenClaw chat error: {message}")
            if state == "aborted":
                raise RuntimeError("OpenClaw chat aborted")

    async def _recv_json(self, ws: Any, timeout: float) -> dict[str, Any]:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Timed out waiting for OpenClaw response") from exc

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")

        try:
            packet = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return packet if isinstance(packet, dict) else {}

    @staticmethod
    def _as_non_empty_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @staticmethod
    def _nested_get(source: Any, *path: str) -> Any:
        value = source
        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    def _resolve_session_key(
        self,
        hello_payload: dict[str, Any],
        requested: Optional[str],
    ) -> Optional[str]:
        if requested and requested.strip():
            return requested.strip()
        for candidate in (
            hello_payload.get("sessionKey"),
            self._nested_get(hello_payload, "snapshot", "sessionDefaults", "mainSessionKey"),
            self._nested_get(hello_payload, "snapshot", "sessionDefaults", "defaultSessionKey"),
        ):
            normalized = self._as_non_empty_str(candidate)
            if normalized:
                return normalized
        return None

    @classmethod
    def _extract_gateway_message_text(cls, message: Any) -> str:
        if message is None:
            return ""
        if isinstance(message, str):
            return cls._clean_text(message)

        parts: list[str] = []
        if isinstance(message, dict):
            direct = message.get("text")
            if isinstance(direct, str):
                parts.append(direct)
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str):
                            parts.append(text)
        return cls._clean_text("\n".join(parts))

    @staticmethod
    def _clean_text(raw: str) -> str:
        text = raw.strip()
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        return text.strip()


class CloudNodeConnector:
    def __init__(self) -> None:
        self.cloud_ws_url = CLOUD_TUNNEL_WS_URL
        self.node_id = CONNECTOR_NODE_ID
        self.owner_user_id = CONNECTOR_OWNER_USER_ID or None
        self.node_token = CONNECTOR_NODE_TOKEN
        self.reconnect_seconds = max(1.0, CONNECTOR_RECONNECT_SECONDS)
        self.heartbeat_seconds = max(5.0, CONNECTOR_HEARTBEAT_SECONDS)
        self.local_client = LocalOpenClawGatewayClient()

    async def run_forever(self) -> None:
        if not self.cloud_ws_url:
            raise RuntimeError("CLOUD_TUNNEL_WS_URL is empty")
        if not self.node_id:
            raise RuntimeError("CONNECTOR_NODE_ID is empty")
        if not self.node_token:
            raise RuntimeError("CONNECTOR_NODE_TOKEN is empty")

        while True:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[%s] cloud tunnel disconnected: %s",
                    CONNECTOR_LOG_PREFIX,
                    exc,
                )
                await asyncio.sleep(self.reconnect_seconds)

    async def _run_once(self) -> None:
        async with websockets.connect(
            self.cloud_ws_url,
            open_timeout=15,
            close_timeout=5,
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "hello",
                        "node_id": self.node_id,
                        "owner_user_id": self.owner_user_id,
                        "node_token": self.node_token,
                        "version": PLUGIN_VERSION,
                        "capabilities": ["chat.request"],
                        "metadata": {"transport": "cloud-ws"},
                    },
                    ensure_ascii=False,
                )
            )

            ack_raw = await asyncio.wait_for(ws.recv(), timeout=10)
            ack_packet = self._decode_packet(ack_raw)
            if ack_packet.get("type") != "hello.ack":
                raise RuntimeError(f"Invalid hello ack: {ack_packet}")

            logger.info("[%s] connected node_id=%s", CONNECTOR_LOG_PREFIX, self.node_id)

            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=self.heartbeat_seconds)
                except asyncio.TimeoutError:
                    await ws.send(
                        json.dumps({"type": "heartbeat", "ts": int(time.time() * 1000)})
                    )
                    continue

                packet = self._decode_packet(raw)
                msg_type = str(packet.get("type") or "").strip().lower()
                if not msg_type:
                    continue
                if msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong", "ts": int(time.time() * 1000)}))
                    continue
                if msg_type == "chat.request":
                    await self._handle_chat_request(ws, packet)

    async def _handle_chat_request(self, ws: Any, packet: dict[str, Any]) -> None:
        request_id = str(packet.get("request_id") or "").strip()
        payload = packet.get("payload")
        if not request_id:
            return
        if not isinstance(payload, dict):
            await self._send_error(ws, request_id, "Missing payload")
            return

        user_message = str(payload.get("user_message") or payload.get("text") or "").strip()
        conversation_id = payload.get("conversation_id")
        if conversation_id is not None:
            conversation_id = str(conversation_id).strip() or None

        if not user_message:
            await self._send_error(ws, request_id, "Empty user_message")
            return

        try:
            data = await self.local_client.chat(
                user_message=user_message,
                conversation_id=conversation_id,
            )
            await ws.send(
                json.dumps(
                    {
                        "type": "chat.response",
                        "request_id": request_id,
                        "ok": True,
                        "data": data,
                    },
                    ensure_ascii=False,
                )
            )
        except ConnectionClosed:
            raise
        except Exception as exc:
            await self._send_error(ws, request_id, str(exc))

    async def _send_error(self, ws: Any, request_id: str, message: str) -> None:
        await ws.send(
            json.dumps(
                {
                    "type": "chat.response",
                    "request_id": request_id,
                    "ok": False,
                    "error": message,
                },
                ensure_ascii=False,
            )
        )

    @staticmethod
    def _decode_packet(raw: Any) -> dict[str, Any]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def run_connector() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    connector = CloudNodeConnector()
    asyncio.run(connector.run_forever())

