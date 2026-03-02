from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class WeChatPluginResponse(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class PluginRegisterPayload(BaseModel):
    plugin_name: str = Field(min_length=1, max_length=64)
    instance_id: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=1, max_length=512)
    version: Optional[str] = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PluginHealthResponse(BaseModel):
    status: str
    plugin_name: str
    instance_id: str
    version: str
    backend_base_url: str
