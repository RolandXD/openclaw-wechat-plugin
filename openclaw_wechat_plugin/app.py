from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .backend_client import backend_client
from .config import (
    BACKEND_BASE_URL,
    DEBUG,
    HOST,
    LOG_LEVEL,
    OPENCLAW_AUTO_REGISTER,
    PLUGIN_AUTO_HEARTBEAT,
    PLUGIN_AUTO_REGISTER,
    PLUGIN_HEARTBEAT_INTERVAL,
    PLUGIN_INSTANCE_ID,
    PLUGIN_NAME,
    PLUGIN_PUBLIC_BASE_URL,
    PLUGIN_VERSION,
    PORT,
)
from .openclaw_gateway import openclaw_gateway_client
from .routes import router

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def plugin_public_base_url() -> str:
    if PLUGIN_PUBLIC_BASE_URL:
        return PLUGIN_PUBLIC_BASE_URL
    if HOST in {"0.0.0.0", "::"}:
        return f"http://127.0.0.1:{PORT}"
    return f"http://{HOST}:{PORT}"


async def _heartbeat_loop() -> None:
    while True:
        try:
            await backend_client.heartbeat()
        except Exception as exc:
            logger.warning("Heartbeat loop error: %s", exc)
        await asyncio.sleep(max(10, PLUGIN_HEARTBEAT_INTERVAL))


@asynccontextmanager
async def lifespan(_: FastAPI):
    heartbeat_task: asyncio.Task | None = None

    if OPENCLAW_AUTO_REGISTER:
        try:
            register_result = await openclaw_gateway_client.register_wechat_plugin(
                plugin_public_base_url()
            )
            logger.info("OpenClaw plugin register success: %s", register_result)
        except Exception as exc:
            logger.warning("OpenClaw plugin register skipped: %s", exc)

    if PLUGIN_AUTO_REGISTER:
        try:
            await backend_client.register()
            logger.info("Backend registry success: %s", PLUGIN_INSTANCE_ID)
        except Exception as exc:
            logger.warning("Backend registry skipped: %s", exc)

    if PLUGIN_AUTO_HEARTBEAT:
        heartbeat_task = asyncio.create_task(_heartbeat_loop())

    yield

    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    application = FastAPI(
        title=f"{PLUGIN_NAME} plugin",
        version=PLUGIN_VERSION,
        debug=DEBUG,
        description="Standalone WeChat plugin service for OpenClaw backend",
        lifespan=lifespan,
    )

    application.include_router(router)

    @application.get("/")
    async def root() -> dict:
        return {
            "plugin": PLUGIN_NAME,
            "instance_id": PLUGIN_INSTANCE_ID,
            "version": PLUGIN_VERSION,
            "backend_base_url": BACKEND_BASE_URL,
            "health": "/health",
            "wechat_message": "/wechat/message",
            "wechat_callback": "/wechat/callback",
            "register_openclaw": "/openclaw/register",
            "register_backend": "/plugin/register",
            "heartbeat": "/plugin/heartbeat",
        }

    return application


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run(
        "openclaw_wechat_plugin.app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
    )
