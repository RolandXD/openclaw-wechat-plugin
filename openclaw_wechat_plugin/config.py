from __future__ import annotations

import os
import socket
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _load_env() -> None:
    # Prefer explicitly provided env file, then project-local .env, then cwd .env.
    explicit = os.getenv("OPENCLAW_WECHAT_PLUGIN_ENV_FILE", "").strip()
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    package_root = Path(__file__).resolve().parents[1]
    candidates.append(package_root / ".env")
    candidates.append(Path.cwd() / ".env")

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            return


_load_env()


def _to_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PLUGIN_NAME = os.getenv("PLUGIN_NAME", "wechat")
PLUGIN_VERSION = os.getenv("PLUGIN_VERSION", "0.2.2")
PLUGIN_INSTANCE_ID = os.getenv(
    "PLUGIN_INSTANCE_ID",
    f"wechat-{socket.gethostname()}-{str(uuid.uuid4())[:8]}",
)
PLUGIN_PUBLIC_BASE_URL = os.getenv("PLUGIN_PUBLIC_BASE_URL", "").strip()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8101"))
DEBUG = _to_bool(os.getenv("DEBUG", "false"), False)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "replace-with-wechat-token")
WECHAT_REQUIRE_SIGNATURE = _to_bool(os.getenv("WECHAT_REQUIRE_SIGNATURE", "true"), True)

BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
BACKEND_MESSAGE_PATH = os.getenv("BACKEND_MESSAGE_PATH", "/wechat/message")
BACKEND_REGISTER_PATH = os.getenv("BACKEND_REGISTER_PATH", "/plugins/register")
BACKEND_HEARTBEAT_PATH = os.getenv("BACKEND_HEARTBEAT_PATH", "/plugins/{instance_id}/heartbeat")
BACKEND_TIMEOUT = float(os.getenv("BACKEND_TIMEOUT", "30"))

PLUGIN_REGISTRY_TOKEN = os.getenv("PLUGIN_REGISTRY_TOKEN", "").strip()
PLUGIN_AUTO_REGISTER = _to_bool(os.getenv("PLUGIN_AUTO_REGISTER", "true"), True)
PLUGIN_AUTO_HEARTBEAT = _to_bool(os.getenv("PLUGIN_AUTO_HEARTBEAT", "false"), False)
PLUGIN_HEARTBEAT_INTERVAL = int(os.getenv("PLUGIN_HEARTBEAT_INTERVAL", "60"))

# OpenClaw gateway registration
OPENCLAW_GATEWAY_WS_URL = os.getenv("OPENCLAW_GATEWAY_WS_URL", "").strip()
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "").strip()
OPENCLAW_TIMEOUT = float(os.getenv("OPENCLAW_TIMEOUT", "15"))
OPENCLAW_CLIENT_ID = os.getenv("OPENCLAW_CLIENT_ID", "gateway-client")
OPENCLAW_CLIENT_MODE = os.getenv("OPENCLAW_CLIENT_MODE", "backend")
OPENCLAW_ROLE = os.getenv("OPENCLAW_ROLE", "operator")
OPENCLAW_AUTO_REGISTER = _to_bool(os.getenv("OPENCLAW_AUTO_REGISTER", "true"), True)
OPENCLAW_APPLY_AFTER_REGISTER = _to_bool(
    os.getenv("OPENCLAW_APPLY_AFTER_REGISTER", "true"),
    True,
)
OPENCLAW_PLUGIN_ENTRY_KEY = os.getenv("OPENCLAW_PLUGIN_ENTRY_KEY", "wechat")
