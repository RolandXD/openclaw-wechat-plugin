from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from .backend_client import backend_client
from .config import (
    BACKEND_BASE_URL,
    HOST,
    OPENCLAW_GATEWAY_WS_URL,
    OPENCLAW_PLUGIN_ENTRY_KEY,
    PLUGIN_INSTANCE_ID,
    PLUGIN_NAME,
    PLUGIN_PUBLIC_BASE_URL,
    PLUGIN_VERSION,
    PORT,
    WECHAT_REQUIRE_SIGNATURE,
    WECHAT_TOKEN,
)
from .models import PluginHealthResponse, WeChatPluginResponse
from .openclaw_gateway import openclaw_gateway_client
from .wechat_crypto import ensure_json_object, verify_signature

logger = logging.getLogger(__name__)

router = APIRouter()


def _plugin_public_base_url() -> str:
    if PLUGIN_PUBLIC_BASE_URL:
        return PLUGIN_PUBLIC_BASE_URL
    if HOST in {"0.0.0.0", "::"}:
        return f"http://127.0.0.1:{PORT}"
    return f"http://{HOST}:{PORT}"


def ensure_signature(
    signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
    *,
    strict: bool,
) -> None:
    has_any = any([signature, timestamp, nonce])

    if not strict and not has_any:
        return

    if not all([signature, timestamp, nonce]):
        raise HTTPException(
            status_code=400,
            detail="Missing signature params: signature, timestamp, nonce",
        )

    if not verify_signature(WECHAT_TOKEN, signature, timestamp, nonce):
        raise HTTPException(status_code=403, detail="Invalid WeChat signature")


async def _forward_message(
    request: Request,
    signature: Optional[str],
    timestamp: Optional[str],
    nonce: Optional[str],
) -> WeChatPluginResponse:
    ensure_signature(
        signature,
        timestamp,
        nonce,
        strict=WECHAT_REQUIRE_SIGNATURE,
    )

    try:
        raw_payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        payload = ensure_json_object(raw_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        response = await backend_client.forward_message(
            payload,
            signature=signature,
            timestamp=timestamp,
            nonce=nonce,
        )
    except RuntimeError as exc:
        logger.error("Forward to backend failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return WeChatPluginResponse.model_validate(response)


@router.get("/health", response_model=PluginHealthResponse)
async def health() -> PluginHealthResponse:
    return PluginHealthResponse(
        status="ok",
        plugin_name=PLUGIN_NAME,
        instance_id=PLUGIN_INSTANCE_ID,
        version=PLUGIN_VERSION,
        backend_base_url=BACKEND_BASE_URL,
    )


@router.get("/wechat/callback", response_class=PlainTextResponse)
async def verify_wechat_callback(
    signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
) -> str:
    ensure_signature(signature, timestamp, nonce, strict=True)
    return echostr


@router.post("/wechat/callback", response_model=WeChatPluginResponse)
async def wechat_callback_message(
    request: Request,
    signature: Optional[str] = Query(default=None),
    timestamp: Optional[str] = Query(default=None),
    nonce: Optional[str] = Query(default=None),
) -> WeChatPluginResponse:
    return await _forward_message(request, signature, timestamp, nonce)


@router.post("/wechat/message", response_model=WeChatPluginResponse)
async def wechat_message(
    request: Request,
    signature: Optional[str] = Query(default=None),
    timestamp: Optional[str] = Query(default=None),
    nonce: Optional[str] = Query(default=None),
) -> WeChatPluginResponse:
    return await _forward_message(request, signature, timestamp, nonce)


@router.post("/plugin/register")
async def register_plugin_now() -> dict:
    try:
        return await backend_client.register()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plugin register failed: {exc}") from exc


@router.post("/plugin/heartbeat")
async def heartbeat_plugin_now() -> dict:
    try:
        return await backend_client.heartbeat()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Plugin heartbeat failed: {exc}") from exc


@router.post("/openclaw/register")
async def register_openclaw_plugin_now() -> dict:
    if not OPENCLAW_GATEWAY_WS_URL:
        raise HTTPException(status_code=400, detail="OPENCLAW_GATEWAY_WS_URL is empty")

    try:
        result = await openclaw_gateway_client.register_wechat_plugin(
            _plugin_public_base_url()
        )
        return {
            "code": 0,
            "message": "success",
            "data": {
                "openclaw_gateway": OPENCLAW_GATEWAY_WS_URL,
                "plugin_entry": OPENCLAW_PLUGIN_ENTRY_KEY,
                "result": result,
            },
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenClaw plugin register failed: {exc}",
        ) from exc
